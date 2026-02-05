import akshare as ak
import pandas as pd
import datetime
from utils import logger, retry

class ValuationEngine:
    def __init__(self):
        # 缓存国债收益率，避免重复请求
        self.cn_10y_yield = None

    @retry(retries=2)
    def _get_bond_yield(self):
        """获取中国10年期国债收益率 (无风险利率锚)"""
        if self.cn_10y_yield: return self.cn_10y_yield
        try:
            # 数据源: 中美国债收益率
            df = ak.bond_zh_us_rate()
            # 取最新一条的'中国国债收益率10年'
            yield_val = df['中国国债收益率10年'].iloc[-1]
            self.cn_10y_yield = yield_val
            return yield_val
        except Exception as e:
            logger.warning(f"国债收益率获取失败: {e}")
            return 2.3 # 兜底值

    @retry(retries=1)
    def get_valuation_status(self, index_code, strategy_type):
        """
        核心功能: 计算估值状态
        返回: multiplier (0.0 - 2.0), status_desc (描述)
        """
        # 1. 如果是黄金/大宗商品/跨境，暂时无法用PE估值，默认适中
        if not index_code or strategy_type == 'commodity':
            return 1.0, "非权益类(默认适中)"

        try:
            # 2. 获取指数估值 (市盈率PE-TTM)
            # symbol 必须是 "沪深300", "全指医药" 这种中文名称或代码
            # akshare 接口: stock_zh_index_value_csindex (中证指数) 或 index_value_hist_funddb
            # 这里为了通用性，我们假设 config.yaml 里配的是指数名称，如 "沪深300"
            
            # 注意：index_value_hist_funddb 比较稳定，支持 "沪深300", "中证500" 等
            df = ak.index_value_hist_funddb(symbol=index_code, indicator="市盈率")
            
            if df.empty: return 1.0, "数据缺失"
            
            current_pe = df['市盈率'].iloc[-1]
            # 取近 5 年 (约1250个交易日) 数据计算分位数
            history = df['市盈率'].tail(1250) 
            percentile = (history < current_pe).mean() # 0.0 - 1.0
            
            # 3. 核心策略逻辑
            
            # A. 核心底仓 (Core): 越跌越买，注重安全边际
            if strategy_type == 'core':
                if percentile < 0.20: return 1.5, f"极度低估(分位{int(percentile*100)}%)"
                if percentile < 0.40: return 1.2, f"低估(分位{int(percentile*100)}%)"
                if percentile > 0.80: return 0.5, f"高估(分位{int(percentile*100)}%)" # 核心仓位高估时少买，但不轻易卖
                if percentile > 0.90: return 0.0, f"极度高估(分位{int(percentile*100)}%)" # 停止定投
                return 1.0, "估值适中"

            # B. 卫星进攻 (Satellite): 趋势优先，但极贵时要跑
            elif strategy_type == 'satellite':
                if percentile < 0.10: return 1.2, "黄金坑(左侧潜伏)"
                if percentile > 0.85: return 0.0, "泡沫预警(禁止买入)" # 卫星仓位高估时坚决不买
                return 1.0, "估值允许博弈"
            
            # C. 红利策略 (Dividend): 看股债性价比 (Fed Model)
            elif strategy_type == 'dividend':
                bond = self._get_bond_yield()
                # 股息率 ≈ 1/PE (粗略估算，更准确应该直接取股息率数据，这里简化)
                # 更好的方式是直接用 index_value_hist_funddb 的 '股息率' 字段
                div_df = ak.index_value_hist_funddb(symbol=index_code, indicator="股息率")
                if not div_df.empty:
                    current_div = div_df['股息率'].iloc[-1]
                    spread = current_div - bond
                    
                    if spread > 2.5: return 2.0, f"历史级机会(息差{spread:.2f}%)"
                    if spread > 1.5: return 1.5, f"高性价比(息差{spread:.2f}%)"
                    if spread < 0: return 0.0, f"性价比消失(息差{spread:.2f}%)"
                return 1.0, "红利适中"

            return 1.0, "逻辑未匹配"

        except Exception as e:
            logger.warning(f"估值计算异常 {index_code}: {e}")
            return 1.0, "估值未知"
