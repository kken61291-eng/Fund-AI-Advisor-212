import akshare as ak
import pandas as pd
import time
import socket
from utils import retry, logger
from news_analyst import NewsAnalyst  # 引入 AI 进行联网搜索

class MarketScanner:
    def __init__(self):
        socket.setdefaulttimeout(5.0)
        # 初始化 AI 用于兜底搜索
        try: self.ai_backup = NewsAnalyst()
        except: self.ai_backup = None

    def _get_column_by_fuzzy(self, df, keywords):
        for col in df.columns:
            col_str = str(col).lower()
            for kw in keywords:
                if kw in col_str:
                    return col
        return None

    def _ai_search_market_status(self, missing_type):
        """
        🚑 数据医生：当 API 挂了，让 AI 去搜最新的市场数据
        """
        if not self.ai_backup: return "数据源故障且AI离线"
        
        query = ""
        if missing_type == "north": query = "今日A股 北向资金 净流入 金额"
        elif missing_type == "sector": query = "今日A股 领涨板块 涨幅榜"
        
        # 搜索
        titles = self.ai_backup.fetch_news_titles(query) # 复用新闻搜索功能
        if not titles: return "搜索无结果"
        
        # 简单归纳
        summary = " | ".join(titles[:3])
        logger.info(f"🚑 AI补全数据 [{missing_type}]: {summary[:30]}...")
        return summary

    @retry(retries=1)
    def get_market_sentiment(self):
        logger.info("📡 扫描市场 (V5.1 联网补全版)...")
        market_data = {
            "north_money": "0",
            "north_label": "数据获取中",
            "top_sectors": [],
            "market_status": "未知"
        }

        # --- 1. 宏观数据 (上证指数 + 联网补全) ---
        try:
            df = ak.stock_zh_index_spot_em(symbol="sh000001")
            if not df.empty:
                pct_col = self._get_column_by_fuzzy(df, ["涨跌幅", "pct", "change"])
                if pct_col:
                    pct_val = float(df.iloc[0][pct_col])
                    market_data['north_money'] = f"{pct_val:+.2f}%"
                    market_data['north_label'] = "上证指数"
                    logger.info(f"✅ 上证锁定: {pct_val:+.2f}%")
            else:
                raise ValueError("上证数据为空")
        except Exception as e:
            logger.warning(f"API获取上证失败: {e} -> 启动AI搜索...")
            # 搜索补救
            web_info = self._ai_search_market_status("north")
            market_data['north_label'] = "AI搜索摘要"
            market_data['north_money'] = "见摘要"
            market_data['market_status'] = web_info # 把搜索结果放这里

        # --- 2. 领涨板块 (API + 联网补全) ---
        try:
            df_sector = ak.stock_board_industry_name_em()
            if not df_sector.empty:
                name_col = self._get_column_by_fuzzy(df_sector, ["名称", "板块", "name"])
                pct_col = self._get_column_by_fuzzy(df_sector, ["涨跌幅", "涨跌", "pct", "change"])

                if name_col and pct_col:
                    df_top = df_sector.sort_values(by=pct_col, ascending=False).head(3)
                    sectors = []
                    for _, row in df_top.iterrows():
                        s_name = row[name_col]
                        s_val = float(row[pct_col])
                        sectors.append(f"{s_name}({s_val:+.2f}%)")
                    
                    market_data['top_sectors'] = sectors
                    logger.info(f"✅ 领涨锁定: {sectors}")
            else:
                raise ValueError("板块数据为空")
        except Exception as e:
            logger.warning(f"API获取板块失败: {e} -> 启动AI搜索...")
            # 搜索补救
            web_info = self._ai_search_market_status("sector")
            market_data['top_sectors'] = [f"AI搜索: {web_info[:20]}..."]

        return market_data
