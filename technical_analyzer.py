import pandas as pd
import numpy as np
from utils import logger

try:
    import ta
except ImportError:
    ta = None

class TechnicalAnalyzer:
    @staticmethod
    def calculate_indicators(data):
        if data is None or data.empty:
            return None
        
        if isinstance(data, dict) and 'daily' in data: df = data['daily']
        else: df = data.copy()

        df = df.sort_index()
        close = df['close']
        volume = df['volume']

        if len(df) < 30:
            logger.warning("数据量不足 30 天，跳过技术分析")
            return None

        res = {
            "price": close.iloc[-1],
            "quant_score": 50,
            "signals": [],
            "risk_factors": {},
            "tech_cro_signal": "PASS",
            "tech_cro_comment": "技术指标正常"
        }

        try:
            if ta:
                rsi_series = ta.momentum.RSIIndicator(close, window=14).rsi()
                res['rsi'] = round(rsi_series.iloc[-1], 2)
                macd = ta.trend.MACD(close)
                hist = macd.macd_diff()
                res['macd'] = {
                    "diff": round(hist.iloc[-1], 3),
                    "trend": "金叉" if hist.iloc[-1] > 0 and hist.iloc[-2] <= 0 else ("死叉" if hist.iloc[-1] < 0 and hist.iloc[-2] >= 0 else ("多头" if hist.iloc[-1] > 0 else "空头"))
                }
                bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
                res['risk_factors']['bollinger_pct_b'] = round(bb.bollinger_pband().iloc[-1], 2)
            else:
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / (loss + 1e-9)
                res['rsi'] = round(100 - (100 / (1 + rs.iloc[-1])), 2)
                res['macd'] = {"trend": "未知"}
                res['risk_factors']['bollinger_pct_b'] = 0.5

            obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
            if len(obv) > 6:
                base_obv = obv.iloc[-6]
                if base_obv == 0: base_obv = 1
                obv_slope = (obv.iloc[-1] - base_obv) / abs(base_obv) * 100
            else:
                obv_slope = 0
            res['flow'] = {"obv_slope": round(obv_slope, 2)}

            window_vr = 26
            df_vr = df.tail(window_vr+1)
            up_vol = df_vr[df_vr['close'] > df_vr['close'].shift(1)]['volume'].sum()
            down_vol = df_vr[df_vr['close'] < df_vr['close'].shift(1)]['volume'].sum()
            
            if down_vol == 0: vr = 5.0
            else: vr = up_vol / down_vol
            res['risk_factors']['vol_ratio'] = round(vr, 2)

            try:
                df_weekly = df.resample('W').agg({'close': 'last'}).dropna()
                if len(df_weekly) >= 5:
                    w_ma5 = df_weekly['close'].rolling(5).mean().iloc[-1]
                    if pd.isna(w_ma5): res['trend_weekly'] = "震荡"
                    else: res['trend_weekly'] = "UP" if df_weekly['close'].iloc[-1] > w_ma5 else "DOWN"
                else: res['trend_weekly'] = "震荡"
            except: res['trend_weekly'] = "数据不足"

            cro_msgs = []
            veto_triggered = False

            if vr < 0.6:
                cro_msgs.append(f"⛔ 量比{vr}极低，禁止开仓")
                veto_triggered = True

            recent_high = close.iloc[-10:].max()
            if res['price'] >= recent_high and res['rsi'] < 60 and res['rsi'] < rsi_series.iloc[-5:].max():
                cro_msgs.append("⚠️ 量价顶背离，建议减仓")
                res['risk_factors']['divergence'] = "顶背离"
            
            if res['trend_weekly'] == "DOWN": cro_msgs.append("📉 周线趋势向下")

            if res['rsi'] > 85:
                cro_msgs.append("🔥 RSI>85 极度超买，禁止追高")
                veto_triggered = True

            if veto_triggered: res['tech_cro_signal'] = "VETO"
            elif cro_msgs: res['tech_cro_signal'] = "WARN"
            
            res['tech_cro_comment'] = " | ".join(cro_msgs) if cro_msgs else "✅ 技术指标健康"

            score = 50
            if 40 <= res['rsi'] <= 60: score += 10
            elif res['rsi'] < 30: score += 20
            elif res['rsi'] > 80: score -= 20
            
            if res['trend_weekly'] == "UP": score += 20
            if "金叉" in res['macd']['trend']: score += 15
            elif "死叉" in res['macd']['trend']: score -= 15
            
            if 0.8 <= vr <= 1.5: score += 5
            elif vr < 0.6: score -= 20

            res['quant_score'] = max(0, min(100, score))
            res['risk_factors']['divergence'] = res['risk_factors'].get('divergence', "无")
            return res

        except Exception as e:
            logger.error(f"指标计算崩溃: {e}")
            return {
                "price": df['close'].iloc[-1] if not df.empty else 0,
                "quant_score": 50,
                "rsi": 50,
                "macd": {"trend": "计算失败", "diff": 0},
                "flow": {"obv_slope": 0},
                "risk_factors": {"vol_ratio": 1.0, "divergence": "无", "bollinger_pct_b": 0.5},
                "trend_weekly": "未知",
                "tech_cro_signal": "PASS",
                "tech_cro_comment": "计算降级"
            }
