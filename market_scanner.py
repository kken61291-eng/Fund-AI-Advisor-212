import akshare as ak
import pandas as pd
from utils import retry, logger
from datetime import datetime

class MarketScanner:
    def __init__(self):
        pass

    @retry(retries=2)
    def get_market_sentiment(self):
        """
        获取宏观市场情绪数据
        1. 北向资金（外资）流向
        2. 行业板块资金流向 Top5
        """
        logger.info("📡 正在扫描全市场资金流向...")
        market_data = {
            "north_money": 0,
            "north_label": "无数据",
            "top_sectors": [],
            "market_status": "震荡"
        }

        try:
            # 1. 获取北向资金 (Smart Money)
            # 接口返回通常是 DataFrame，取最新的一行
            df_north = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
            # 格式清洗，获取最新值
            if not df_north.empty:
                latest_val = df_north.iloc[-1]['value'] # 单位通常是万元
                # 转换为亿元
                net_inflow = latest_val / 10000 
                market_data['north_money'] = round(net_inflow, 2)
                
                if net_inflow > 20: market_data['north_label'] = "大幅流入 (利好)"
                elif net_inflow > 0: market_data['north_label'] = "小幅流入 (温和)"
                elif net_inflow > -20: market_data['north_label'] = "小幅流出 (承压)"
                else: market_data['north_label'] = "大幅流出 (利空)"

            # 2. 获取行业板块资金流向 (找风口)
            df_sector = ak.stock_board_industry_name_em(indicator="资金流向")
            # 按【主力净流入】排序，取前5名
            df_top = df_sector.sort_values(by="主力净流入", ascending=False).head(5)
            
            sectors = []
            for _, row in df_top.iterrows():
                # 转换单位为亿
                flow = round(row['主力净流入'] / 100000000, 2)
                sectors.append(f"{row['板块名称']}(+{flow}亿)")
            
            market_data['top_sectors'] = sectors
            logger.info(f"市场扫描完成: 北向 {market_data['north_money']}亿 | 热点: {sectors}")

        except Exception as e:
            logger.error(f"市场扫描部分失败: {e}")
            market_data['north_label'] = "数据获取失败"

        return market_data
