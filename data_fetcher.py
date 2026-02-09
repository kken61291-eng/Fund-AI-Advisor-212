import akshare as ak
import pandas as pd
import time
import random
from datetime import datetime
from utils import logger, retry

class DataFetcher:
    def __init__(self):
        # [V15.7] 扩充 User-Agent 池以绕过东财封锁
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
        ]

    def _get_random_header(self):
        return {"User-Agent": random.choice(self.user_agents)}

    @retry(retries=3, delay=2)
    def get_fund_history(self, fund_code, days=250):
        """
        获取K线数据。优先级：东财 -> 新浪 -> 腾讯(备用)
        """
        try:
            # 1. 尝试东财 (数据最全)
            # 增加随机延迟，防止被认定为攻击
            time.sleep(random.uniform(1.0, 3.0)) 
            
            df = ak.fund_etf_hist_em(
                symbol=fund_code, 
                period="daily", 
                start_date="20240101", 
                end_date="20500101",
                adjust="qfq"
            )
            
            # 格式标准化
            # 东财返回列名通常为: 日期, 开盘, 收盘, 最高, 最低, 成交量, ...
            df.rename(columns={'日期':'date', '开盘':'open', '收盘':'close', '最高':'high', '最低':'low', '成交量':'volume'}, inplace=True)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            if df.empty: raise ValueError("EM returned empty data")
            return df

        except Exception as e:
            logger.warning(f"⚠️ 东财源受阻/失败 {fund_code}: {str(e)[:50]}... 切换新浪源。")
            return self._fetch_sina_fallback(fund_code)

    def _fetch_sina_fallback(self, fund_code):
        """
        备用源：新浪财经
        [修复] 兼容新浪可能返回的不同列名格式
        """
        try:
            time.sleep(1) # 稍作等待
            df = ak.fund_etf_hist_sina(symbol=fund_code)
            
            # 打印列名以便调试 (如果 DEBUG_MODE 开启)
            # print(f"DEBUG Sina Columns: {df.columns}")

            # 新浪可能返回英文列名 date, open, high, low, close, volume
            # 也可能返回中文。这里做全兼容重命名。
            rename_map = {
                '日期': 'date', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume',
                '开盘': 'open', '最高': 'high', '最低': 'low', '收盘': 'close', '成交量': 'volume'
            }
            df.rename(columns=rename_map, inplace=True)
            
            # 确保 date 列存在
            if 'date' not in df.columns and df.index.name == 'date':
                df = df.reset_index()

            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # 确保包含核心字段
            required_cols = ['open', 'close', 'high', 'low', 'volume']
            if not all(col in df.columns for col in required_cols):
                raise ValueError(f"Sina missing columns: {df.columns}")

            if not df.empty:
                logger.info(f"🔄 [备用源] 新浪接力成功: {fund_code}")
                return df
            else:
                logger.error(f"❌ 新浪源返回空数据: {fund_code}")
                return None
        except Exception as e:
            logger.error(f"❌ 新浪源接力失败 {fund_code}: {e}")
            return None
