import akshare as ak
import pandas as pd
import time
import random
from datetime import datetime
from utils import logger, retry

class DataFetcher:
    def __init__(self):
        # [V15.9] 扩充 User-Agent 池
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
        ]

    def _get_random_header(self):
        return {"User-Agent": random.choice(self.user_agents)}

    @retry(retries=3, delay=5) 
    def get_fund_history(self, fund_code, days=250):
        # 1. 尝试东财 (数据最全)
        try:
            # 随机延迟防止封禁
            sleep_time = random.uniform(3.0, 6.0)
            time.sleep(sleep_time)
            
            df = ak.fund_etf_hist_em(
                symbol=fund_code, 
                period="daily", 
                start_date="20240101", 
                end_date="20500101", 
                adjust="qfq"
            )
            
            rename_map = {'日期':'date', '开盘':'open', '收盘':'close', '最高':'high', '最低':'low', '成交量':'volume'}
            df.rename(columns=rename_map, inplace=True)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            if not df.empty:
                logger.info(f"✅ [主源] 东财获取成功: {fund_code}")
                return df
            
        except Exception as e:
            logger.warning(f"⚠️ 东财源受阻 {fund_code}: {str(e)[:50]}... 切换备用源。")

        # 2. 尝试新浪 (备用)
        return self._fetch_sina_fallback(fund_code)

    def _fetch_sina_fallback(self, fund_code):
        try:
            logger.info(f"🔄 [备用源] 正在尝试新浪源: {fund_code}...")
            time.sleep(2) 
            df = ak.fund_etf_hist_sina(symbol=fund_code)
            
            # [调试] 如果解析失败，我们需要知道列名到底是什么
            raw_columns = list(df.columns)
            
            if df.index.name in ['date', '日期']:
                df = df.reset_index()
            
            # 暴力清洗列名：假设前6列是 OHLCV
            if len(df.columns) >= 6:
                df.columns = ['date', 'open', 'high', 'low', 'close', 'volume'] + list(df.columns[6:])
            
            # 再次检查 date
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)

                if not df.empty:
                    logger.info(f"✅ [备用源] 新浪获取成功: {fund_code}")
                    return df
            
            # 如果走到这里，说明 date 列还是没找到
            logger.error(f"❌ 新浪源列名解析失败 {fund_code} | 原始列名: {raw_columns}")
            return None

        except Exception as e:
            logger.error(f"❌ 所有真实数据源均失败 {fund_code}: {e}")
            return None
