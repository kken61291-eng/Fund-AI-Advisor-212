import pandas as pd
import ta
from utils import logger

class TechnicalAnalyzer:
    @staticmethod
    def calculate_indicators(df):
        """
        计算技术指标 (Python 侧预计算)
        """
        if df.empty or len(df) < 30: return {}

        # 1. RSI
        rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi().iloc[-1]

        # 2. MACD
        macd = ta.trend.MACD(df['close'])
        macd_diff = macd.macd_diff().iloc[-1]
        
        # 3. 均线趋势 (MA20)
        ma20 = ta.trend.SMAIndicator(df['close'], window=20).sma_indicator().iloc[-1]
        price = df['close'].iloc[-1]
        trend_status = "BULL" if price > ma20 else "BEAR"
        
        return {
            "rsi": round(rsi, 2),
            "macd_signal": "GOLD_CROSS" if macd_diff > 0 else "DEAD_CROSS",
            "trend": trend_status,
            "price_vs_ma20": round((price - ma20) / ma20 * 100, 2) # 乖离率
        }

    @staticmethod
    def check_weekly_trend(weekly_df):
        """
        周线过滤器：判断大趋势
        """
        if weekly_df.empty or len(weekly_df) < 20: return "UNKNOWN"
        
        # 计算周线 MA20
        ma20_weekly = ta.trend.SMAIndicator(weekly_df['close'], window=20).sma_indicator().iloc[-1]
        current_weekly_close = weekly_df['close'].iloc[-1]
        
        return "UP" if current_weekly_close > ma20_weekly else "DOWN"
