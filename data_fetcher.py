import akshare as ak
import tushare as ts
import pandas as pd
import os
from datetime import datetime, timedelta
from utils import retry, logger

class DataFetcher:
    def __init__(self):
        # 初始化 Tushare，作为最后的救命稻草
        self.ts_token = os.getenv("TUSHARE_TOKEN")
        self.pro = None
        if self.ts_token:
            try:
                ts.set_token(self.ts_token)
                self.pro = ts.pro_api()
            except Exception as e:
                logger.warning(f"Tushare 初始化警告: {e}")

    @retry(retries=1, backoff_factor=1)
    def _fetch_em(self, code):
        """来源1: 东方财富 (AkShare - 容易被GitHub封IP)"""
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
        """来源2: 新浪财经 (AkShare - 备用爬虫)"""
        try:
            symbol = f"sh{code}" if code.startswith("5") else f"sz{code}"
            df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
            # 新浪接口通常自带 volume 字段
            return df
        except: return None

    @retry(retries=2, backoff_factor=2)
    def _fetch_tushare(self, code):
        """
        来源3: Tushare Pro (官方API - 抗封锁核心)
        当上面两个都因为IP问题挂掉时，这个能救命。
        """
        if not self.pro: return None
        try:
            # 格式转换：510300 -> 510300.SH
            ts_code = f"{code}.SH" if code.startswith("5") else f"{code}.SZ"
            
            # 获取过去一年的数据，保证足够计算周线
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
            
            # 专门获取基金日线
            df = self.pro.fund_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            
            if df is None or df.empty: return None
                
            # Tushare 返回字段映射: trade_date->date, vol->volume
            df = df.rename(columns={
                "trade_date": "date", 
                "vol": "volume"
            })
            # Tushare 数据默认是倒序的（最新在最前），需要转为正序
            df = df.sort_values('date')
            return df
        except Exception as e:
            logger.error(f"Tushare 获取异常 {code}: {e}")
            return None

    def get_fund_history(self, code):
        """
        V10.3 数据获取主逻辑
        逻辑链：尝试 EM -> 失败 -> 尝试 Sina -> 失败 -> 启动 Tushare
        """
        df = None
        source_name = ""

        # 1. 优先尝试免费的 AkShare (EM)
        df = self._fetch_em(code)
        if df is not None and not df.empty: source_name = "EM"
        
        # 2. 其次尝试 AkShare (Sina)
        if df is None or df.empty:
            df = self._fetch_sina(code)
            if df is not None and not df.empty: source_name = "Sina"

        # 3. [关键逻辑] 如果都失败，使用 Tushare API
        if df is None or df.empty:
            if self.ts_token:
                # logger.info(f"启动 Tushare 救援: {code}")
                df = self._fetch_tushare(code)
                if df is not None and not df.empty: source_name = "Tushare"
            else:
                logger.warning("未配置 Tushare Token，无法救援")

        # 4. 最终检查
        if df is None or df.empty:
            logger.error(f"❌ 数据全线获取失败: {code}")
            return None

        try:
            # 数据清洗 (Standardization)
            if 'volume' not in df.columns: df['volume'] = 0 # 兜底防止报错
            
            df['date'] = pd.to_datetime(df['date'])
            df['close'] = pd.to_numeric(df['close'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            df['volume'] = pd.to_numeric(df['volume'])
            
            df = df.sort_values('date').set_index('date')
            
            # 生成真周线 (Resample)
            weekly_df = df.resample('W-FRI').agg({
                'close': 'last', 
                'high': 'max', 
                'low': 'min', 
                'volume': 'sum'
            }).dropna()
            
            # 确保数据量足够计算 MACD/MA20
            if len(weekly_df) < 5: return None

            return {"daily": df, "weekly": weekly_df}

        except Exception as e:
            logger.error(f"数据清洗失败 {code} [{source_name}]: {e}")
            return None
