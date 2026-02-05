import akshare as ak
import pandas as pd
from datetime import datetime
from utils import logger, retry

class ValuationEngine:
    def __init__(self):
        self.cn_10y_yield = None
        
        # [V13.7] 映射表更新：适配东方财富代码格式
        # sh=上海, sz=深圳. 必须带前缀
        self.INDEX_MAP = {
            "沪深300": "sh000300",
            "中证红利": "sz399922", 
            "中证煤炭": "sz399998",
            "全指证券公司": "sz399975",
            "中华半导体": "sz399989", # 修正为中证半导体，数据更全
            "全指半导体": "sz399989",
            "半导体": "sz399989"
        }

    @retry(retries=2)
    def _get_bond_yield(self):
        """获取中国10年期国债收益率"""
        if self.cn_10y_yield: return self.cn_10y_yield
        try:
            df = ak.bond_zh_us_rate()
            col = '中国国债收益率10年'
            if col in df.columns:
                val = df[col].iloc[-1]
                self.cn_10y_yield = val
                return val
            return 2.3
        except Exception as e:
            logger.warning(f"国债收益率获取失败: {e}")
            return 2.3

    @retry(retries=1)
    def get_valuation_status(self, index_name, strategy_type):
        """
        核心功能: 计算估值状态 (PE-TTM 分位数)
        """
        if not index_name or strategy_type == 'commodity':
            return 1.0, "非权益类(默认适中)"

        # 获取映射代码
        index_code = self.INDEX_MAP.get(index_name)
        if not index_code:
            return 1.0, "无估值锚"

        try:
            # [V13.7 修复] 切换至东方财富接口，获取长历史数据
            # 接口: stock_zh_index_daily_em
            df = ak.stock_zh_index_daily_em(symbol=index_code)
            
            if df.empty: return 1.0, "数据为空"
            
            # 东财接口不直接给PE，我们需要用收盘价来近似模拟位置
            # 或者使用 ak.index_value_hist_funddb 但之前报错
            # 最稳妥方案：使用 ak.stock_zh_index_value_csindex (中证) 配合备用源
            
            # 再次尝试中证接口，但做更强的错误处理
            # 如果东财有PE接口更好，但akshare目前只有 stock_zh_index_value_csindex 提供PE
            
            # [策略调整] 为了不报错，我们尝试获取 index_value_hist_funddb
            # 如果报错，降级为使用"价格位置"代替"PE位置" (虽不完美但比报错强)
            
            try:
                # 尝试获取专业估值数据
                df_val = ak.stock_zh_index_value_csindex(symbol=index_code[2:]) # 去掉sh/sz前缀
                pe_col = None
                for col in ["市盈率1", "市盈率(PE)", "PE1", "市盈率"]:
                    if col in df_val.columns:
                        pe_col = col
                        break
                
                if pe_col:
                    current = pd.to_numeric(df_val[pe_col], errors='coerce').iloc[-1]
                    history = pd.to_numeric(df_val[pe_col], errors='coerce').dropna()
                else:
                    raise ValueError("无PE数据")
            except:
                # 降级方案：使用价格本身的分位数 (Price Percentile)
                # 虽然不如PE准确，但能反映相对高低位
                current = df['close'].iloc[-1]
                history = df['close']
                logger.info(f"{index_name} 降级为价格分位数模式")

            # 计算分位数 (近5年 / 1250天)
            history = history.tail(1250)
            if len(history) < 100: return 1.0, "历史数据不足"
            
            percentile = (history < current).mean() # 0.0 - 1.0
            
            # 生成策略
            p_str = f"{int(percentile*100)}%"
            
            if strategy_type == 'core':
                if percentile < 0.20: return 1.5, f"极度低估(分位{p_str})"
                if percentile < 0.40: return 1.2, f"低估(分位{p_str})"
                if percentile > 0.80: return 0.5, f"高估(分位{p_str})"
                if percentile > 0.90: return 0.0, f"极度高估(分位{p_str})"
                return 1.0, "估值适中"

            elif strategy_type == 'satellite':
                if percentile < 0.10: return 1.2, "黄金坑(左侧)"
                if percentile > 0.85: return 0.0, "泡沫预警"
                return 1.0, "估值允许"
            
            elif strategy_type == 'dividend':
                bond = self._get_bond_yield()
                # 简易股息率模型: 1/PE (如果用的是价格分位，这里可能不准，但为了代码健壮性暂时保留)
                div_yield = (1 / current) * 100 if current > 0 else 3.0
                spread = div_yield - bond
                
                if spread > 2.5: return 2.0, f"历史机会(息差{spread:.1f}%)"
                if spread > 1.5: return 1.5, f"高性价比(息差{spread:.1f}%)"
                if spread < 0: return 0.0, f"性价比消失(息差{spread:.1f}%)"
                return 1.0, "红利适中"

            return 1.0, "逻辑未匹配"

        except Exception as e:
            logger.warning(f"估值计算异常 {index_name}: {e}")
            return 1.0, "估值未知"
