import akshare as ak
import pandas as pd
from utils import retry, logger

class DataFetcher:
    @retry(retries=3)
    def get_fund_history(self, code):
        try:
            # 优先 ETF
            try:
                df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="qfq")
                df = df.rename(columns={"日期":"date", "收盘":"close", "最高":"high", "最低":"low"})
            except:
                df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
                df = df.rename(columns={"净值日期":"date", "单位净值":"close"})
                df['high'] = df['close']; df['low'] = df['close']

            if df is None or df.empty: return None
            df['date'] = pd.to_datetime(df['date'])
            df['close'] = pd.to_numeric(df['close'])
            df = df.sort_values('date').set_index('date')
            
            # 真周线
            weekly = df.resample('W-FRI').agg({'close':'last', 'high':'max', 'low':'min'}).dropna()
            return {"daily": df, "weekly": weekly}
        except: return None
