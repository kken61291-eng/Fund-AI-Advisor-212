import akshare as ak
import pandas as pd
from utils import retry, logger

class DataFetcher:
    def __init__(self):
        # V9.0: 移除 Tushare 依赖，专注于 AkShare 的多源切换
        pass

    @retry(retries=1, backoff_factor=1)
    def _fetch_em(self, code):
        """
        来源1: 东方财富 (EastMoney)
        数据最全，但在 GitHub Actions 环境容易被封 IP
        """
        try:
            # 接口：场内ETF历史行情
            df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
            df = df.rename(columns={
                "日期": "date", 
                "收盘": "close", 
                "最高": "high", 
                "最低": "low", 
                "开盘": "open"
            })
            return df
        except: 
            return None

    @retry(retries=2, backoff_factor=2)
    def _fetch_sina(self, code):
        """
        来源2: 新浪财经 (Sina)
        抗封锁能力极强，作为稳健的备用源
        """
        try:
            # 新浪接口需要区分 sh/sz 前缀
            # 5开头是沪市(sh)，1开头是深市(sz)，其他尝试推断
            if code.startswith("5"):
                symbol = f"sh{code}"
            elif code.startswith("1") or code.startswith("0") or code.startswith("3"):
                symbol = f"sz{code}" # ETF通常是159开头
            else:
                symbol = f"sh{code}" # 默认尝试sh

            # 接口：A股个股历史行情 (ETF在交易所视为股票，通用)
            df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
            
            # 新浪返回的列名通常是英文，但为了保险做一次映射
            # akshare 的 stock_zh_a_daily 通常返回: date, open, high, low, close, volume...
            return df
        except: 
            return None

    def get_fund_history(self, code):
        """
        V9.0 主逻辑：多源自动切换 + 真周线生成
        """
        df = None
        source_name = ""

        # --- 第一步：尝试主力源 (东方财富) ---
        df = self._fetch_em(code)
        if df is not None and not df.empty:
            source_name = "EM"
        
        # --- 第二步：如果失败，切换备用源 (新浪财经) ---
        else:
            # logger.warning(f"⚠️ 东方财富获取失败 {code}，切换至新浪财经...")
            df = self._fetch_sina(code)
            if df is not None and not df.empty:
                source_name = "Sina"

        # --- 第三步：如果都失败，报错返回 ---
        if df is None or df.empty:
            logger.error(f"❌ 所有数据源均获取失败: {code} (可能是代码错误或IP全被封)")
            return None

        try:
            # --- 数据清洗与标准化 ---
            # 确保列名存在
            required_cols = ['date', 'close', 'high', 'low']
            for col in required_cols:
                if col not in df.columns:
                    # 尝试兼容新浪可能的列名差异
                    if col == 'date' and 'date' not in df.columns: df['date'] = df.index
            
            df['date'] = pd.to_datetime(df['date'])
            df['close'] = pd.to_numeric(df['close'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            
            # 按日期排序并设为索引
            df = df.sort_values('date').set_index('date')
            
            # --- 生成真周线 (周五聚合) ---
            # 逻辑：取每周最后一个交易日的收盘价，每周最高价，每周最低价
            weekly_df = df.resample('W-FRI').agg({
                'close': 'last',
                'high': 'max',
                'low': 'min'
            }).dropna()
            
            # 简单校验
            if len(weekly_df) < 10:
                return None

            return {
                "daily": df,
                "weekly": weekly_df
            }

        except Exception as e:
            logger.error(f"数据清洗失败 {code} [{source_name}]: {e}")
            return None
