import akshare as ak
import requests
import re
from datetime import datetime
from utils import logger, retry

class MarketScanner:
    def __init__(self):
        pass

    @retry(retries=2, delay=2) 
    def get_macro_news(self):
        """
        获取宏观新闻 (东方财富全球快讯 - 极稳版)
        """
        news_list = []
        try:
            # [核心修复] 改用东财全球财经快讯
            # 接口: stock_info_global_ems (东方财富)
            df = ak.stock_info_global_ems()
            
            # 宏观关键词库
            keywords = ["央行", "加息", "降息", "GDP", "CPI", "美联储", "战争", "重磅", "国务院", "A股", "人民币", "PMI", "黄金", "原油"]
            
            count = 0
            for _, row in df.iterrows():
                content = str(row.get('content', ''))
                title = str(row.get('title', ''))
                
                # 东财快讯有时候只有 content
                if not title or title == 'nan':
                    title = content[:40] + "..."
                
                full_text = title + content
                
                # 筛选包含关键词的重要新闻
                if any(k in full_text for k in keywords):
                    news_list.append({
                        "title": title.replace('\n', ' '),
                        "source": "东方财富",
                        "time": row.get('public_time', '')
                    })
                    count += 1
                    if count >= 5: break
            
            if not news_list:
                return [{"title": "市场平静，无重大宏观异动。", "source": "MarketScanner"}]
                
            return news_list
            
        except Exception as e:
            logger.warning(f"宏观新闻获取失败: {e}")
            return [{"title": "宏观数据源暂时不可用，请关注技术面。", "source": "系统提示"}]

    def get_sector_news(self, keyword):
        return []
