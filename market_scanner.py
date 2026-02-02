import akshare as ak
import pandas as pd
from utils import retry, logger
from datetime import datetime

class MarketScanner:
    def __init__(self):
        pass

    def _get_column_by_keyword(self, df, keywords):
        """
        辅助函数：在DataFrame中模糊查找包含任一关键词的列名
        """
        for col in df.columns:
            for kw in keywords:
                if kw in str(col):
                    return col
        return None

    @retry(retries=2)
    def get_market_sentiment(self):
        logger.info("📡 正在获取市场资金数据 (V2.1)...")
        market_data = {
            "north_money": 0,
            "north_label": "无数据",
            "top_sectors": [],
            "market_status": "震荡"
        }

        # --- 1. 获取北向资金 (改用历史接口，更稳) ---
        try:
            # 获取沪深港通历史数据 (symbol="北上")
            # 这是一个非常稳定的接口，返回过去每天的数据
            df_north = ak.stock_hsgt_hist_em(symbol="北上")
            
            if not df_north.empty:
                # 取最后一行（最近一个交易日）
                latest = df_north.iloc[-1]
                
                # 找数值列：通常叫 "当日净流入" 或 "净流入"
                col_name = self._get_column_by_keyword(df_north, ["净流入", "value"])
                
                if col_name:
                    val_raw = float(latest[col_name])
                    
                    # 单位换算：接口通常返回 亿元 (比如 12.5) 或 元
                    # 东方财富历史接口通常直接返回 亿元 单位
                    # 我们做个判断：如果数值 > 10000，说明是万元或元，需要除
                    # 如果数值 < 1000，说明已经是亿元了
                    
                    if abs(val_raw) > 100000000: # 可能是元
                        net_inflow = round(val_raw / 100000000, 2)
                    elif abs(val_raw) > 10000:   # 可能是万元
                        net_inflow = round(val_raw / 10000, 2)
                    else:                        # 应该是亿元
                        net_inflow = round(val_raw, 2)

                    market_data['north_money'] = net_inflow
                    
                    # 情绪打标签
                    if net_inflow > 20: market_data['north_label'] = "大幅流入"
                    elif net_inflow > 0: market_data['north_label'] = "小幅流入"
                    elif net_inflow > -20: market_data['north_label'] = "小幅流出"
                    else: market_data['north_label'] = "大幅流出"
                    
                    logger.info(f"✅ 北向资金锁定: {net_inflow}亿 (列名:{col_name})")
                else:
                    logger.warning(f"❌ 北向资金列名匹配失败: {df_north.columns}")
        except Exception as e:
            logger.error(f"北向资金获取异常: {e}")

        # --- 2. 获取板块资金流向 ---
        try:
            # 行业资金流向
            df_sector = ak.stock_board_industry_name_em(indicator="资金流向")
            
            if not df_sector.empty:
                # 找排序列：通常叫 "主力净流入"
                sort_col = self._get_column_by_keyword(df_sector, ["主力净流入", "净流入"])
                name_col = self._get_column_by_keyword(df_sector, ["板块名称", "名称", "板块"])

                if sort_col and name_col:
                    # 按资金流入倒序
                    df_top = df_sector.sort_values(by=sort_col, ascending=False).head(5)
                    
                    sectors = []
                    for _, row in df_top.iterrows():
                        s_name = row[name_col]
                        s_val_raw = float(row[sort_col])
                        
                        # 板块接口通常返回的是 "元" (很大一串数字)
                        # 比如 1500000000 -> 15.0亿
                        s_val_billion = round(s_val_raw / 100000000, 2)
                        
                        sectors.append(f"{s_name}({s_val_billion}亿)")
                    
                    market_data['top_sectors'] = sectors
                    logger.info(f"✅ 主力板块锁定: {sectors}")
                else:
                    logger.warning(f"❌ 板块列名匹配失败: {df_sector.columns}")
        except Exception as e:
            logger.error(f"板块资金获取异常: {e}")

        return market_data
