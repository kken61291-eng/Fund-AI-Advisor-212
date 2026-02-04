import akshare as ak
import yfinance as yf
import pandas as pd
import time
from utils import retry, logger

class DataFetcher:
    def __init__(self):
        pass

    @retry(retries=1, backoff_factor=1)
    def _fetch_em(self, code):
        """来源1: 东方财富 (国内IP首选，GitHub易挂)"""
        try:
            df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
            df = df.rename(columns={
                "日期": "date", "收盘": "close", "最高": "high", 
                "最低": "low", "开盘": "open", "成交量": "volume"
            })
            return df
        except: return None

    @retry(retries=1, backoff_factor=1)
    def _fetch_sina(self, code):
        """来源2: 新浪财经 (备用)"""
        try:
            symbol = f"sh{code}" if code.startswith("5") else f"sz{code}"
            df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
            return df
        except: return None

    @retry(retries=3, backoff_factor=2)
    def _fetch_yahoo(self, code):
        """
        来源3: Yahoo Finance (国际通用，GitHub可用，完全免费)
        """
        try:
            # 1. 转换代码格式
            # 上海(5/6开头) -> .SS, 深圳(1/0/3开头) -> .SZ
            if code.startswith('5') or code.startswith('6'):
                yahoo_symbol = f"{code}.SS"
            else:
                yahoo_symbol = f"{code}.SZ"
            
            # 2. 获取数据 (下载最近1年，确保有足够周线)
            # progress=False 关闭进度条防止日志混乱
            ticker = yf.Ticker(yahoo_symbol)
            df = ticker.history(period="1y", auto_adjust=True)
            
            if df is None or df.empty:
                return None
            
            # 3. 清洗数据
            # Yahoo 返回的索引就是 Date，列名是 Open, High, Low, Close, Volume
            df = df.reset_index()
            df = df.rename(columns={
                "Date": "date", 
                "Open": "open", 
                "High": "high", 
                "Low": "low", 
                "Close": "close", 
                "Volume": "volume"
            })
            
            # 转换时区，去掉时分秒
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            
            return df
        except Exception as e:
            logger.error(f"Yahoo 获取失败 {code}: {e}")
            return None

    def get_fund_history(self, code):
        """
        V10.4 逻辑: EM -> Sina -> Yahoo(救世主)
        """
        df = None
        source_name = ""

        # 1. 尝试国内接口 (EM)
        df = self._fetch_em(code)
        if df is not None and not df.empty: source_name = "EM"
        
        # 2. 尝试国内接口 (Sina)
        if df is None or df.empty:
            df = self._fetch_sina(code)
            if df is not None and not df.empty: source_name = "Sina"

        # 3. [核心] 尝试 Yahoo Finance
        if df is None or df.empty:
            # logger.info(f"启动 Yahoo 救援: {code}")
            df = self._fetch_yahoo(code)
            if df is not None and not df.empty: source_name = "Yahoo"

        if df is None or df.empty:
            logger.error(f"❌ 所有源均失败: {code}")
            return None

        try:
            # 标准化处理
            if 'volume' not in df.columns: df['volume'] = 0
            
            df['date'] = pd.to_datetime(df['date'])
            df['close'] = pd.to_numeric(df['close'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            df['volume'] = pd.to_numeric(df['volume'])
            
            df = df.sort_values('date').set_index('date')
            
            # 生成周线
            weekly_df = df.resample('W-FRI').agg({
                'close': 'last', 
                'high': 'max', 
                'low': 'min', 
                'volume': 'sum'
            }).dropna()
            
            if len(weekly_df) < 5: return None

            return {"daily": df, "weekly": weekly_df}

        except Exception as e:
            logger.error(f"数据清洗失败 {code} [{source_name}]: {e}")
            return None
