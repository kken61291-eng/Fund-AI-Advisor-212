import akshare as ak
import pandas as pd
import os
import datetime
import time
import yaml
import warnings
from utils import logger, retry

# 忽略 pandas 的一些 future warnings，保持日志清爽
warnings.simplefilter(action='ignore', category=FutureWarning)

class DataFetcher:
    def __init__(self, data_dir="data_market"):
        self.data_dir = data_dir
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def _get_file_path(self, code):
        return os.path.join(self.data_dir, f"{code}.csv")

    @retry(retries=3, delay=2)
    def fetch_fund_daily(self, code):
        """
        [核心下载逻辑] 获取场内ETF日线数据
        优先使用 ak.fund_etf_hist_em (东财接口)
        """
        try:
            # 东财接口
            df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date="20200101", end_date="20500101")
            
            if df is None or df.empty:
                logger.warning(f"⚠️ [DataFetcher] {code} 接口返回为空")
                return None

            # 标准化列名 (东财返回的是中文)
            rename_map = {
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "涨跌幅": "pct_chg",
                "涨跌额": "change",
                "换手率": "turnover"
            }
            df = df.rename(columns=rename_map)
            
            # 确保日期格式正确
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            df = df.sort_values('date', ascending=True)
            
            # 保留核心列，过滤掉杂项
            cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
            cols = [c for c in cols if c in df.columns]
            df = df[cols]
            
            return df
        except Exception as e:
            logger.error(f"❌ [DataFetcher] {code} 下载异常: {e}")
            raise e

    def get_fund_history(self, code, force_update=False):
        """
        获取基金历史数据 (智能缓存机制)
        1. force_update=True: 强制联网下载并覆盖保存 (爬虫模式)
        2. force_update=False: 优先读本地，本地没有才下载 (分析模式)
        """
        file_path = self._get_file_path(code)
        
        # 1. [读模式] 尝试读取本地
        if os.path.exists(file_path) and not force_update:
            try:
                df = pd.read_csv(file_path)
                if not df.empty:
                    last_date = df['date'].iloc[-1]
                    logger.info(f"📅 [本地缓存] {code} 最新日期: {last_date} | ⏸️ 历史数据就绪")
                    return df
            except Exception as e:
                logger.warning(f"⚠️ 读取缓存失败 {code}: {e}，将尝试重新下载")

        # 2. [写模式] 下载新数据
        logger.info(f"⬇️ [正在下载] {code} 行情数据...")
        df_new = self.fetch_fund_daily(code)
        
        if df_new is not None:
            df_new.to_csv(file_path, index=False)
            logger.info(f"✅ [已保存] {code} 更新至 {df_new['date'].iloc[-1]}")
            return df_new
        
        return None

# ==========================================
# [V15.14 核心新增] 独立运行入口
# 使得 python data_fetcher.py 可以作为爬虫独立运行
# ==========================================
if __name__ == "__main__":
    print("🚀 [MarketCrawler] 启动批量行情更新任务...")
    
    # 1. 读取 Config
    def load_config_local():
        try:
            with open('config.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except:
            print("❌ Config not found")
            return {}

    cfg = load_config_local()
    funds = cfg.get('funds', [])
    
    if not funds:
        print("⚠️ 未找到基金列表，请检查 config.yaml")
        exit()

    # 2. 初始化抓取器
    fetcher = DataFetcher()
    success_count = 0
    
    # 3. 循环抓取
    for fund in funds:
        code = fund.get('code')
        name = fund.get('name')
        print(f"🔄 Processing: {name} ({code})")
        
        try:
            # 强制更新模式 (force_update=True)
            result = fetcher.get_fund_history(code, force_update=True)
            if result is not None:
                success_count += 1
            # 防封限流
            time.sleep(1.5) 
        except Exception as e:
            print(f"❌ Error updating {name}: {e}")
        
    print(f"🏁 行情更新完毕: 成功 {success_count}/{len(funds)}")
