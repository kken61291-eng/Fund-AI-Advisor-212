import akshare as ak
import tushare as ts
import pandas as pd
import os
from utils import retry, logger

class DataFetcher:
    def __init__(self):
        # 初始化 Tushare (如果有 Token)
        self.ts_token = os.getenv("TUSHARE_TOKEN")
        if self.ts_token:
            ts.set_token(self.ts_token)
            self.pro = ts.pro_api()
        else:
            logger.warning("未检测到 TUSHARE_TOKEN，将仅使用 Akshare")

    @retry(retries=3)
    def get_fund_data_v4(self, code, fund_type):
        """
        获取综合数据：日线、周线、实时溢价
        """
        data_packet = {
            "daily_df": pd.DataFrame(),
            "weekly_df": pd.DataFrame(),
            "realtime_premium": 0.0,
            "name": code
        }

        # 1. 获取日线历史数据 (以 Akshare 为主，稳定且免费)
        try:
            # 简化处理：统一获取 ETF 或 基金净值
            if fund_type == "fund":
                df = ak.fund_open_fund_info_em(fund=code, indicator="单位净值走势")
                df = df.rename(columns={"净值日期": "date", "单位净值": "close"})
            else:
                # ETF 处理
                df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
                df = df.rename(columns={"日期": "date", "收盘": "close", "开盘": "open", "最高": "high", "最低": "low", "成交量": "volume"})
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').set_index('date')
            data_packet['daily_df'] = df
            
            # 2. Python 降维打击：直接生成周线数据
            # 逻辑：利用 pandas resample 将日线聚合为周线，节省一次 API 请求
            weekly_df = df.resample('W').agg({
                'close': 'last',
                'open': 'first', # 如果有
                'high': 'max',   # 如果有
                'low': 'min'     # 如果有
            }).dropna()
            data_packet['weekly_df'] = weekly_df

        except Exception as e:
            logger.error(f"历史数据获取失败 {code}: {e}")

        # 3. 获取实时溢价 (仅针对 ETF)
        if "etf" in fund_type:
            try:
                # 获取实时价格
                spot = ak.stock_zh_index_spot_em(symbol=code) # 这是一个通用接口，有时需要换
                # 简单起见，这里假设你能获取到 (ETF 实时接口变动频繁，需根据实际调整)
                # 这里用伪代码逻辑展示架构
                current_price = float(df.iloc[-1]['close']) # 暂用收盘价代替
                
                # 获取 I.O.P.V (估算净值) - 这里可以用 Tushare
                if self.ts_token:
                    # Tushare 获取基金基本信息
                    # df_fund = self.pro.fund_nav(ts_code=f'{code}.SH')
                    pass
                
                # 计算溢价率 (模拟)
                # premium = (current_price - net_value) / net_value
                data_packet['realtime_premium'] = 0.0 # 占位，需对接实时接口
                
            except Exception as e:
                logger.warning(f"溢价率计算失败: {e}")

        return data_packet
