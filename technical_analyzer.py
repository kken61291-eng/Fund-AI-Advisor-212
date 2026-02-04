import pandas as pd
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import SMAIndicator, MACD
from ta.volatility import AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator
from utils import logger

class TechnicalAnalyzer:
    @staticmethod
    def calculate_indicators(data_dict):
        """
        V10.2 技术指标计算 (防崩版)
        """
        try:
            df = data_dict['daily'].copy()
            weekly_df = data_dict['weekly'].copy()
            
            if len(df) < 60: return None

            current_price = df['close'].iloc[-1]
            
            # --- 1. 基础指标 ---
            rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
            
            ma20 = SMAIndicator(df['close'], window=20).sma_indicator().iloc[-1]
            bias_20 = (current_price - ma20) / ma20 * 100
            
            atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().iloc[-1]
            
            # --- 2. 进阶指标 ---
            # MACD
            macd_obj = MACD(df['close'])
            macd_line = macd_obj.macd().iloc[-1]
            macd_signal = macd_obj.macd_signal().iloc[-1]
            macd_hist = macd_obj.macd_diff().iloc[-1]
            
            # KDJ (Stoch)
            stoch = StochasticOscillator(df['high'], df['low'], df['close'], window=9, smooth_window=3)
            k_val = stoch.stoch().iloc[-1]
            d_val = stoch.stoch_signal().iloc[-1]
            j_val = 3 * k_val - 2 * d_val

            # [关键修复] 资金流向代理 (OBV) - 增加容错判断
            obv_slope = 0
            # 只有当 'volume' 列存在且数值不全为0时才计算 OBV
            if 'volume' in df.columns and df['volume'].sum() > 0:
                try:
                    obv = OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume()
                    if len(obv) >= 6:
                        obv_curr = obv.iloc[-1]
                        obv_prev = obv.iloc[-6]
                        if obv_prev != 0:
                            obv_slope = (obv_curr - obv_prev) / abs(obv_prev) * 100
                except:
                    pass # 如果OBV计算出错，默认为0，不影响其他指标
            
            # --- 3. 周线趋势 ---
            trend_weekly = "NEUTRAL"
            if len(weekly_df) >= 20:
                w_ma20 = SMAIndicator(weekly_df['close'], window=20).sma_indicator().iloc[-1]
                w_price = weekly_df['close'].iloc[-1]
                trend_weekly = "UP" if w_price > w_ma20 else "DOWN"

            # --- 4. 打分模型 ---
            score = 50
            
            if rsi < 30: score += 25
            elif rsi < 40: score += 10
            elif rsi > 80: score -= 25
            elif rsi > 70: score -= 15
            
            if trend_weekly == "UP": score += 20
            else: score -= 20
            
            if bias_20 < -7: score += 15
            if bias_20 > 15: score -= 15
            
            if macd_hist > 0:
                if macd_line > macd_signal: score += 10
            else:
                score -= 10
            
            if obv_slope > 5: score += 10
            elif obv_slope < -5: score -= 10

            if j_val < 0: score += 5 
            if j_val > 100: score -= 5

            return {
                "price": current_price,
                "quant_score": int(max(0, min(100, score))),
                "rsi": round(rsi, 2),
                "bias_20": round(bias_20, 2),
                "trend_weekly": trend_weekly,
                "atr": round(atr, 3),
                "macd": {
                    "diff": round(macd_hist, 3), 
                    "trend": "金叉" if (macd_hist > 0 and macd_line > macd_signal) else ("死叉" if macd_hist < 0 else "震荡")
                },
                "kdj": {"j": round(j_val, 2)},
                "flow": {"obv_slope": round(obv_slope, 2)}
            }
        except Exception as e:
            logger.error(f"指标计算错误: {e}")
            return None
