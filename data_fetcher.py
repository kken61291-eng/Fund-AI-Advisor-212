import akshare as ak
import tushare as ts
import pandas as pd
import os
import datetime
from utils import retry, logger

class DataFetcher:
    def __init__(self):
        # 【关键】从环境变量读取 Token，不写死在代码里
        self.ts_token = os.getenv("TUSHARE_TOKEN")
        self.pro = None
        
        if self.ts_token:
            try:
                ts.set_token(self.ts_token)
                self.pro = ts.pro_api()
                logger.info("✅ Tushare 初始化成功")
            except Exception as e:
                logger.warning(f"Tushare 初始化失败: {e}")
        else:
            logger.info("ℹ️ 未检测到 TUSHARE_TOKEN，将使用纯 Akshare 模式")

    @retry(retries=3)
    def get_fund_history(self, code):
        """
        获取日线数据，并自动生成周线数据 (V4.0)
        返回: {'daily': df, 'weekly': df}
        """
        try:
            # 1. 获取日线 (使用 Akshare 开放基金接口，适配性最好)
            # 这里的 indicator="单位净值走势" 可以获取场外基金的历史净值
            df = ak.fund_open_fund_info_em(fund=code, indicator="单位净值走势")
            
            # 清洗数据
            df = df.rename(columns={"净值日期": "date", "单位净值": "close"})
            df['date'] = pd.to_datetime(df['date'])
            df['close'] = pd.to_numeric(df['close'])
            df = df.sort_values('date').set_index('date')
            
            # 2. 生成周线 (Resample) - Python 预计算省一次 API
            # 'W' 代表 Weekly
            weekly_df = df.resample('W').agg({'close': 'last'}).dropna()

            return {
                "daily": df,
                "weekly": weekly_df
            }
        except Exception as e:
            logger.error(f"数据获取失败 {code}: {e}")
            return {"daily": pd.DataFrame(), "weekly": pd.DataFrame()}
