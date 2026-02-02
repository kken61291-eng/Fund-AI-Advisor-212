import akshare as ak
import pandas as pd
from utils import retry, logger
from datetime import datetime

class MarketScanner:
    def __init__(self):
        pass

    def _get_column_by_keyword(self, df, keywords):
        """辅助函数：模糊查找列名"""
        for col in df.columns:
            for kw in keywords:
                if kw in str(col):
                    return col
        return None

    @retry(retries=2)
    def get_market_sentiment(self):
        logger.info("📡 正在获取市场资金数据 (V2.2 修复版)...")
        market_data = {
            "north_money": 0,
            "north_label": "无数据",
            "top_sectors": [],
            "market_status": "震荡"
        }

        # --- 1. 获取北向资金 (修复参数) ---
        try:
            # 【修复点】symbol必须是 "北向" (之前写成"北上"了)
            df_north = ak.stock_hsgt_hist_em(symbol="北向")
            
            if not df_north.empty:
                latest = df_north.iloc[-1]
                # 模糊找 "净流入" 列
                col_name = self._get_column_by_keyword(df_north, ["净流入", "value"])
                
                if col_name:
                    val_raw = float(latest[col_name])
                    
                    # 单位自适应 (亿/万/元)
                    if abs(val_raw) > 100000000: 
                        net_inflow = round(val_raw / 100000000, 2)
                    elif abs(val_raw) > 10000:
                        net_inflow = round(val_raw / 10000, 2)
                    else:
                        net_inflow = round(val_raw, 2)

                    market_data['north_money'] = net_inflow
                    
                    if net_inflow > 20: market_data['north_label'] = "大幅流入"
                    elif net_inflow > 0: market_data['north_label'] = "小幅流入"
                    elif net_inflow > -20: market_data['north_label'] = "小幅流出"
                    else: market_data['north_label'] = "大幅流出"
                    
                    logger.info(f"✅ 北向资金锁定: {net_inflow}亿")
                else:
                    logger.warning(f"❌ 北向资金列名失败: {df_north.columns}")
        except Exception as e:
            logger.error(f"北向资金获取异常: {e}")

        # --- 2. 获取板块资金流向 (修复参数) ---
        try:
            # 【修复点】移除 indicator 参数，直接调用
            df_sector = ak.stock_board_industry_name_em()
            
            if not df_sector.empty:
                # 模糊找 "主力净流入" 和 "板块名称"
                sort_col = self._get_column_by_keyword(df_sector, ["主力净流入", "净流入"])
                name_col = self._get_column_by_keyword(df_sector, ["板块名称", "名称"])

                if sort_col and name_col:
                    # 按资金流入倒序
                    df_top = df_sector.sort_values(by=sort_col, ascending=False).head(5)
                    
                    sectors = []
                    for _, row in df_top.iterrows():
                        s_name = row[name_col]
                        s_val_raw = float(row[sort_col])
                        # 板块资金通常很大，转亿
                        s_val_billion = round(s_val_raw / 100000000, 2)
                        sectors.append(f"{s_name}({s_val_billion}亿)")
                    
                    market_data['top_sectors'] = sectors
                    logger.info(f"✅ 主力板块锁定: {sectors}")
                else:
                    logger.warning(f"❌ 板块列名匹配失败: {df_sector.columns}")
        except Exception as e:
            logger.error(f"板块资金获取异常: {e}")

        return market_data
