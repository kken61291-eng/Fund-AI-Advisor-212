import akshare as ak
import pandas as pd
import time
import random
import requests
from datetime import datetime, timedelta
from utils import logger, retry

try:
    import yfinance as yf
except ImportError:
    yf = None

class DataFetcher:
    def __init__(self):
        # [V14.22] 浏览器伪装头，防止被东财秒封
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    @retry(retries=2, delay=3)
    def get_fund_history(self, code, period='3y'):
        """
        获取基金/股票历史数据 (增强反爬 + 随机延迟)
        """
        # [策略] 每次请求前随机休息 1-3 秒，模拟人类行为
        time.sleep(random.uniform(1.5, 3.5))

        # 1. 尝试 AkShare (东财源)
        try:
            symbol = code
            if not code.startswith('sh') and not code.startswith('sz'):
                symbol = f"sh{code}" if code.startswith('5') or code.startswith('6') else f"sz{code}"
            
            # 使用 akshare 内部接口
            df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date="20200101", end_date="20500101")
            
            if not df.empty:
                df = df.rename(columns={"日期": "date", "收盘": "close", "最高": "high", "最低": "low", "开盘": "open", "成交量": "volume"})
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                if df.index.tz is not None: df.index = df.index.tz_localize(None)
                return df
        except Exception as e:
            logger.warning(f"东财源受阻 {code} (云端IP可能被限): {str(e)[:100]}... 尝试切换通道")

        # 2. 尝试 AkShare (新浪源) - 备用
        try:
            time.sleep(2) # 冷却一下
            symbol = f"sh{code}" if code.startswith('5') or code.startswith('6') else f"sz{code}"
            df = ak.stock_zh_index_daily(symbol=symbol)
            if not df.empty:
                df = df.rename(columns={"date": "date", "close": "close", "high": "high", "low": "low", "open": "open", "volume": "volume"})
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                if df.index.tz is not None: df.index = df.index.tz_localize(None)
                return df
        except Exception:
            pass

        # 3. 兜底 Yahoo Finance (国际源 - 对 GitHub Actions 最友好)
        if yf:
            try:
                time.sleep(2)
                logger.info(f"启动 Yahoo 国际线路兜底: {code}")
                suffix = ".SS" if code.startswith('5') or code.startswith('6') else ".SZ"
                symbol = code + suffix
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="2y")
                if not df.empty:
                    df = df.rename(columns={"Close": "close", "High": "high", "Low": "low", "Open": "open", "Volume": "volume"})
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    return df
            except Exception as e:
                logger.error(f"Yahoo 获取失败 {code}: {e}")

        logger.error(f"❌ 所有数据源均无法连接: {code}")
        return None
