import akshare as ak
import pandas as pd
import os
import tushare as ts
import time
from datetime import datetime
from utils import logger, retry

class ValuationEngine:
    def __init__(self):
        self.cn_10y_yield = None
        self.tushare_api = None
        
        # 初始化 Tushare (如果有 Token)
        token = os.getenv("TUSHARE_TOKEN")
        if token:
            try:
                self.tushare_api = ts.pro_api(token)
            except:
                pass

        # 静态映射表
        # 格式: 标准名 -> [东财代码, 新浪代码, Tushare代码]
        self.INDEX_MAP = {
            "沪深300":      {"em": "sh000300", "sina": "sh000300", "ts": "000300.SH"},
            "中证红利":      {"em": "sz399922", "sina": "sz399922", "ts": "399922.SZ"},
            "中证煤炭":      {"em": "sz399998", "sina": "sz399998", "ts": "399998.SZ"},
            "全指证券公司":  {"em": "sz399975", "sina": "sz399975", "ts": "399975.SZ"},
            "中华半导体":    {"em": "sz399989", "sina": "sz399989", "ts": "399989.SZ"}, # 映射为中证半导体
            "全指半导体":    {"em": "sz399989", "sina": "sz399989", "ts": "399989.SZ"},
            "中证传媒":      {"em": "sz399971", "sina": "sz399971", "ts": "399971.SZ"}
        }

    @retry(retries=2, delay=2)
    def _get_bond_yield(self):
        """获取国债收益率"""
        if self.cn_10y_yield: return self.cn_10y_yield
        try:
            df = ak.bond_zh_us_rate()
            val = df['中国国债收益率10年'].iloc[-1]
            self.cn_10y_yield = val
            return val
        except: return 2.3

    def _fetch_history_data(self, index_name):
        """
        [V13.8 核心] 三级容灾获取历史数据
        返回: pandas Series (历史收盘价或PE)
        """
        codes = self.INDEX_MAP.get(index_name)
        if not codes: return None

        # 1. 尝试 东方财富 (EastMoney)
        try:
            df = ak.stock_zh_index_daily_em(symbol=codes['em'])
            return df['close']
        except Exception as e:
            logger.warning(f"[{index_name}] 东财源受阻，切换备用源... ({str(e)[:50]})")

        # 2. 尝试 新浪财经 (Sina) - 极稳
        try:
            time.sleep(1) # 礼貌延迟
            df = ak.stock_zh_index_daily(symbol=codes['sina'])
            return df['close']
        except Exception as e:
            logger.warning(f"[{index_name}] 新浪源受阻... ({str(e)[:50]})")

        # 3. 尝试 Tushare Pro (如果有 Token)
        if self.tushare_api:
            try:
                time.sleep(1)
                # 获取指数日线
                end_dt = datetime.now().strftime("%Y%m%d")
                start_dt = (datetime.now() - pd.Timedelta(days=2000)).strftime("%Y%m%d")
                df = self.tushare_api.index_daily(ts_code=codes['ts'], start_date=start_dt, end_date=end_dt)
                if not df.empty:
                    # Tushare 返回是倒序的，需要转正序
                    return df.sort_values('trade_date')['close']
            except Exception as e:
                logger.warning(f"[{index_name}] Tushare源受阻... ({str(e)[:50]})")

        return None

    def get_valuation_status(self, index_name, strategy_type):
        """计算估值状态"""
        if not index_name or strategy_type == 'commodity':
            return 1.0, "非权益类(默认适中)"

        try:
            # 获取历史数据 (三源容灾)
            history = self._fetch_history_data(index_name)
            
            if history is None or len(history) < 100:
                return 1.0, "数据源全线不可用"

            # 计算分位数
            current = history.iloc[-1]
            # 取近5年 (1250天)
            history_window = history.tail(1250)
            percentile = (history_window < current).mean()
            
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
                # 简易股息率模型: 1/PE ≈ (1/Price) * K (K为常数，这里简化处理，主要看趋势)
                # 实战中，价格分位极低通常意味着股息率极高
                div_yield = (1 / current) * 100 if current > 0 else 3.0 # 仅作趋势参考
                
                # 更准确的红利策略：直接用分位数判断
                if percentile < 0.10: return 2.0, f"历史大底(分位{p_str})"
                if percentile < 0.30: return 1.5, f"低估区域(分位{p_str})"
                if percentile > 0.80: return 0.0, f"性价比低(分位{p_str})"
                return 1.0, "红利适中"

            return 1.0, "逻辑未匹配"

        except Exception as e:
            logger.warning(f"估值计算严重错误 {index_name}: {e}")
            return 1.0, "估值未知"
