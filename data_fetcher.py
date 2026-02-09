import akshare as ak
import pandas as pd
import time
import random
from datetime import datetime
from utils import logger, retry

class DataFetcher:
    def __init__(self):
        # [V15.6] Dynamic User-Agent Pool to bypass EM blocks
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        ]

    def _get_random_header(self):
        return {"User-Agent": random.choice(self.user_agents)}

    @retry(retries=3, delay=2)
    def get_fund_history(self, fund_code, days=250):
        """
        Fetch K-line data. Priority: EastMoney (akshare) -> Sina (fallback)
        """
        try:
            # 1. Attempt EastMoney (Most detailed)
            # Add a slight jitter to prevent burst requests being blocked
            time.sleep(random.uniform(0.1, 0.5))
            
            df = ak.fund_etf_hist_em(
                symbol=fund_code, 
                period="daily", 
                start_date="20240101", 
                end_date="20500101",
                adjust="qfq"
            )
            
            # Format standardization
            df.rename(columns={'日期':'date', '开盘':'open', '收盘':'close', '最高':'high', '最低':'low', '成交量':'volume'}, inplace=True)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            if df.empty: raise ValueError("EM returned empty data")
            return df

        except Exception as e:
            logger.warning(f"⚠️ EastMoney Blocked/Fail {fund_code}: {str(e)[:50]}... Switching to Sina.")
            return self._fetch_sina_fallback(fund_code)

    def _fetch_sina_fallback(self, fund_code):
        """
        Fallback to Sina Finance if EM fails.
        """
        try:
            time.sleep(1) # Wait a bit before fallback
            df = ak.fund_etf_hist_sina(symbol=fund_code)
            
            df.rename(columns={'date':'date', 'open':'open', 'close':'close', 'high':'high', 'low':'low', 'volume':'volume'}, inplace=True)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            if not df.empty:
                logger.info(f"🔄 [Fallback] Sina Success: {fund_code}")
                return df
            else:
                logger.error(f"❌ Sina also returned empty for {fund_code}")
                return None
        except Exception as e:
            logger.error(f"❌ Sina Fallback Failed {fund_code}: {e}")
            return None
