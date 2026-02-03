import pandas as pd
import ta
from utils import logger

class TechnicalAnalyzer:
    @staticmethod
    def calculate_indicators(df_dict):
        daily = df_dict.get('daily')
        weekly = df_dict.get('weekly')
        if daily is None or daily.empty or len(daily) < 60: return None

        try:
            close = daily['close'].iloc[-1]
            high = daily['high'] if 'high' in daily else daily['close']
            low = daily['low'] if 'low' in daily else daily['close']
            
            rsi = ta.momentum.RSIIndicator(daily['close'], window=14).rsi().iloc[-1]
            ma20 = ta.trend.SMAIndicator(daily['close'], window=20).sma_indicator().iloc[-1]
            bias = (close - ma20) / ma20 * 100
            
            # ATR Volatility
            atr_ind = ta.volatility.AverageTrueRange(high, low, daily['close'], window=14)
            cur_atr = atr_ind.average_true_range().iloc[-1]
            mean_atr = atr_ind.average_true_range().rolling(60).mean().iloc[-1]
            high_vol = cur_atr > mean_atr * 1.5

            # Trend
            t_day = "BULL" if close > ma20 else "BEAR"
            t_week = "UNKNOWN"
            if weekly is not None and len(weekly) > 20:
                w_ma20 = ta.trend.SMAIndicator(weekly['close'], window=20).sma_indicator().iloc[-1]
                t_week = "UP" if weekly['close'].iloc[-1] > w_ma20 else "DOWN"

            # Score
            score = 0
            reasons = []
            
            if t_week == "UP": score += 40; reasons.append("周线多头")
            elif t_week == "DOWN": score -= 20; reasons.append("周线空头")
            
            if rsi < 30: score += 40; reasons.append("RSI极度超卖")
            elif rsi < 40: score += 20; reasons.append("RSI弱势区")
            elif rsi > 70: score -= 30; reasons.append("RSI超买")
            
            if bias < -5: score += 15; reasons.append("乖离深跌")
            elif bias > 5: score -= 10; reasons.append("乖离过大")
            
            if t_day == "BULL" and rsi < 60: score += 20; reasons.append("日线健康")
            elif t_day == "BEAR" and rsi > 40: score -= 10; reasons.append("日线空头反抽")
            
            if high_vol: score *= 0.8; reasons.append("⚠️[高波动]打折")
            if t_week == "DOWN" and t_day == "BULL": score = min(score, 45); reasons.append("⚠️[风控]下跌中继")
            
            return {
                "price": round(close, 4), "rsi": round(rsi, 2), "bias_20": round(bias, 2),
                "trend_weekly": t_week, "quant_score": int(score), "quant_reasons": reasons
            }
        except: return None
