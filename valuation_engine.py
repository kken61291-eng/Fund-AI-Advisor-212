import pandas as pd
import numpy as np
from utils import logger

class ValuationEngine:
    def __init__(self):
        pass

    def get_valuation_status(self, fund_code, current_data):
        """
        [零网络版] 直接利用已获取的 ETF 历史数据计算估值分位
        
        Args:
            fund_code: ETF 代码 (仅用于日志)
            current_data: 包含历史数据的 DataFrame (由 DataFetcher 提供)
            
        Returns: 
            (multiplier, description)
        """
        try:
            # 1. 数据校验
            if current_data is None or current_data.empty:
                return 1.0, "数据缺失"
            
            # 使用 'close' 列
            if 'close' in current_data.columns:
                history_series = current_data['close']
            elif '收盘' in current_data.columns:
                history_series = current_data['收盘']
            else:
                return 1.0, "数据列错误"

            # 2. 确保数据长度足够
            if len(history_series) < 120:
                return 1.0, "数据不足"

            # 3. 计算分位点 (Percentile)
            window_len = min(1250, len(history_series))
            window_data = history_series.tail(window_len)
            
            current_price = window_data.iloc[-1]
            low_val = window_data.min()
            high_val = window_data.max()
            
            if high_val <= low_val:
                percentile = 0.5
            else:
                percentile = (current_price - low_val) / (high_val - low_val)
            
            p_str = f"{int(percentile*100)}%"
            
            # 4. 通用估值策略矩阵
            if percentile < 0.10: 
                return 1.6, f"极低估(P:{p_str})"
            elif percentile < 0.25: 
                return 1.3, f"低估(P:{p_str})"
            elif percentile < 0.40: 
                return 1.1, f"偏低(P:{p_str})"
            elif percentile > 0.85: 
                return 0.5, f"高估(P:{p_str})"
            elif percentile > 0.95: 
                return 0.0, f"泡沫(P:{p_str})"
            else:
                return 1.0, f"适中(P:{p_str})"

        except Exception as e:
            logger.error(f"估值计算异常 {fund_code}: {e}")
            return 1.0, "计算错误"
