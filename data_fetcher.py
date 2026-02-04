import akshare as ak
import yfinance as yf
import pandas as pd
import socket
import time
from utils import retry, logger

class DataFetcher:
    def __init__(self):
        pass

    @retry(retries=1, backoff_factor=1)
    def _fetch_em(self, code):
        """来源1: 东方财富"""
        try:
            # 临时设置超时防止假死
            socket.setdefaulttimeout(15)
            df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
            df = df.rename(columns={
                "日期": "date", "收盘": "close", "最高": "high", 
                "最低": "low", "开盘": "open", "成交量": "volume"
            })
            return df
        except: return None
        finally:
            # 恢复默认超时，以免影响后续 LLM 调用
            socket.setdefaulttimeout(None)

    @retry(retries=1, backoff_factor=1)
    def _fetch_sina(self, code):
        """来源2: 新浪财经"""
        try:
            socket.setdefaulttimeout(15)
            symbol = f"sh{code}" if code.startswith("5") else f"sz{code}"
            df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
            return df
        except: return None
        finally:
            socket.setdefaulttimeout(None)

    @retry(retries=2, backoff_factor=2)
    def _fetch_yahoo(self, code):
        """
        来源3: Yahoo Finance (国际通用)
        [V10.6] 增加 socket 超时控制，防止卡死
        """
        try:
            # ⚠️ 关键：设置 20秒 强制超时
            # 如果 Yahoo 20秒不说话，直接杀掉连接，抛出异常
            socket.setdefaulttimeout(20)
            
            # 转换代码
            if code.startswith('5') or code.startswith('6'):
                yahoo_symbol = f"{code}.SS"
            else:
                yahoo_symbol = f"{code}.SZ"
            
            # 获取数据
            ticker = yf.Ticker(yahoo_symbol)
            df = ticker.history(period="1y", auto_adjust=True)
            
            if df is None or df.empty:
                return None
            
            # 清洗
            df = df.reset_index()
            df = df.rename(columns={
                "Date": "date", "Open": "open", "High": "high", 
                "Low": "low", "Close": "close", "Volume": "volume"
            })
            
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            return df
            
        except Exception as e:
            logger.error(f"Yahoo 获取失败 {code}: {e}")
            return None
        finally:
            # ⚠️ 必须恢复！否则会影响 OpenAI/Kimi 的长文本生成
            socket.setdefaulttimeout(None)

    def get_fund_history(self, code):
        """
        V10.6 逻辑: EM -> Sina -> Yahoo
        """
        df = None
        source_name = ""

        # 1. EM
        df = self._fetch_em(code)
        if df is not None and not df.empty: source_name = "EM"
        
        # 2. Sina
        if df is None or df.empty:
            df = self._fetch_sina(code)
            if df is not None and not df.empty: source_name = "Sina"

        # 3. Yahoo (带超时保护)
        if df is None or df.empty:
            df = self._fetch_yahoo(code)
            if df is not None and not df.empty: source_name = "Yahoo"

        if df is None or df.empty:
            logger.error(f"❌ 所有源均失败: {code}")
            return None

        try:
            if 'volume' not in df.columns: df['volume'] = 0
            
            df['date'] = pd.to_datetime(df['date'])
            df['close'] = pd.to_numeric(df['close'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            df['volume'] = pd.to_numeric(df['volume'])
            
            df = df.sort_values('date').set_index('date')
            
            weekly_df = df.resample('W-FRI').agg({
                'close': 'last', 'high': 'max', 'low': 'min', 'volume': 'sum'
            }).dropna()
            
            if len(weekly_df) < 5: return None

            return {"daily": df, "weekly": weekly_df}

        except Exception as e:
            logger.error(f"数据清洗失败 {code} [{source_name}]: {e}")
            return None
