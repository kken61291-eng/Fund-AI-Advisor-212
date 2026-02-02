import akshare as ak
import pandas as pd
import ta
from utils import retry, logger
from datetime import datetime, timedelta

class DataFetcher:
    def __init__(self):
        pass

    @retry(retries=3)
    def get_fund_history(self, code, fund_type="fund"):
        """
        获取基金历史净值并计算技术指标
        fund_type: 'fund'(场外基金) 或 'etf'(场内ETF)
        """
        # 默认取过去90天数据
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
        
        logger.info(f"正在获取基金 {code} 的数据...")
        
        df = None
        
        try:
            if fund_type == "fund":
                # 场外基金接口
                df = ak.fund_open_fund_info_em(fund=code, indicator="单位净值走势")
                df = df.rename(columns={"净值日期": "date", "单位净值": "close"})
            else:
                # ETF 接口（需要转换代码格式）
                if code.startswith("5") or code.startswith("1"):
                    # 沪市
                    symbol = f"sh{code}"
                else:
                    # 深市
                    symbol = f"sz{code}"
                df = ak.fund_etf_hist_sina(symbol=symbol)
                df = df.rename(columns={"date": "date", "close": "close"})
                
        except Exception as e:
            logger.error(f"获取数据失败: {e}")
            raise ValueError(f"未能获取到基金 {code} 的数据")

        if df is None or df.empty:
            raise ValueError(f"基金 {code} 返回数据为空")

        # 数据清洗
        df['date'] = pd.to_datetime(df['date'])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close'])
        df = df.sort_values('date')

        if len(df) < 20:
            raise ValueError(f"基金 {code} 数据不足，无法计算指标")

        # --- 技术指标计算 ---
        # 1. RSI (相对强弱指数)
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        
        # 2. MACD
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        # 3. MA20 (20日均线)
        df['ma20'] = ta.trend.sma_indicator(df['close'], window=20)
        
        # 4. 计算偏离度（用于判断超买超卖程度）
        latest = df.iloc[-1]
        deviation = (latest['close'] - latest['ma20']) / latest['ma20'] * 100
        
        # 返回最近的一条数据用于决策
        latest_data = latest.to_dict()
        latest_data['price_position'] = 'bull' if latest['close'] > latest['ma20'] else 'bear'
        latest_data['ma_deviation'] = deviation  # 价格偏离20日均线的百分比
        
        return latest_data