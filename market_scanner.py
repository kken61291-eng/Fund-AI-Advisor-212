import akshare as ak
import pandas as pd
import time
from utils import retry, logger

class MarketScanner:
    def __init__(self):
        pass

    def _get_column_by_fuzzy(self, df, keywords):
        """超级模糊查找"""
        for col in df.columns:
            col_str = str(col).lower()
            for kw in keywords:
                if kw in col_str:
                    return col
        return None

    def _fetch_shanghai_index(self):
        """B计划：获取上证指数"""
        try:
            df = ak.stock_zh_index_daily_em(symbol="sh000001")
            if not df.empty:
                latest = df.iloc[-1]
                close = float(latest['close'])
                prev_close = float(df.iloc[-2]['close'])
                pct = ((close - prev_close) / prev_close) * 100
                return pct
        except:
            return 0.0
        return 0.0

    @retry(retries=2)
    def get_market_sentiment(self):
        logger.info("📡 正在扫描全市场 (V4.1 修复版)...")
        market_data = {
            "north_money": 0,
            "north_label": "数据暂缺",
            "top_sectors": [],
            "market_status": "震荡"
        }

        # --- 1. 获取北向资金 ---
        try:
            total_inflow = 0
            success_count = 0
            
            # 【关键修复】增加 "净买额" 以匹配 "当日成交净买额"
            value_keywords = ["净流入", "净买入", "净买额", "value", "amount", "成交净买入"]

            for symbol in ["沪股通", "深股通"]:
                try:
                    df = ak.stock_hsgt_hist_em(symbol=symbol)
                    if not df.empty:
                        col = self._get_column_by_fuzzy(df, value_keywords)
                        if col:
                            val = float(df.iloc[-1][col])
                            if abs(val) > 10000: val /= 10000 # 转亿
                            total_inflow += val
                            success_count += 1
                        else:
                            logger.warning(f"❌ {symbol} 列名未识别: {df.columns}")
                except Exception as ex:
                    logger.warning(f"{symbol} 获取微瑕: {ex}")
            
            if success_count > 0:
                net_inflow = round(total_inflow, 2)
                market_data['north_money'] = net_inflow
                market_data['north_label'] = "北向资金"
                
                if net_inflow > 20: status = "大幅流入"
                elif net_inflow > 0: status = "小幅流入"
                elif net_inflow > -20: status = "小幅流出"
                else: status = "大幅流出"
                
                market_data['north_label'] = f"{status}"
                logger.info(f"✅ 北向资金锁定: {net_inflow}亿")
            else:
                logger.warning("⚠️ 北向资金失败，启用B计划(上证指数)...")
                sh_pct = self._fetch_shanghai_index()
                market_data['north_money'] = f"{sh_pct:.2f}%"
                market_data['north_label'] = "上证指数"
                
        except Exception as e:
            logger.error(f"宏观数据异常: {e}")

        # --- 2. 获取领涨板块 ---
        sector_success = False
        for attempt in range(3):
            try:
                df_sector = ak.stock_board_industry_name_em()
                if not df_sector.empty:
                    name_col = self._get_column_by_fuzzy(df_sector, ["名称", "板块", "name"])
                    pct_col = self._get_column_by_fuzzy(df_sector, ["涨跌幅", "涨跌", "pct", "change"])

                    if name_col and pct_col:
                        df_top = df_sector.sort_values(by=pct_col, ascending=False).head(5)
                        sectors = []
                        for _, row in df_top.iterrows():
                            s_name = row[name_col]
                            s_val = float(row[pct_col])
                            sectors.append(f"{s_name}({s_val:+.2f}%)")
                        
                        market_data['top_sectors'] = sectors
                        logger.info(f"✅ 领涨板块锁定: {sectors}")
                        sector_success = True
                        break
                    else:
                        logger.warning(f"板块列名未识别: {df_sector.columns}")
            except Exception as e:
                time.sleep(3)

        if not sector_success:
             market_data['top_sectors'] = ["网络波动，暂无数据"]

        return market_data
