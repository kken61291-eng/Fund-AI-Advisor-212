import akshare as ak
import requests
import re
from datetime import datetime
from utils import logger, retry

class MarketScanner:
    def __init__(self):
        pass

    @retry(retries=2, delay=2)  # [修复] backoff_factor -> delay
    def get_macro_news(self):
        """
        获取宏观新闻 (财联社电报)
        """
        news_list = []
        try:
            # 接口: cls_telegraph_news
            df = ak.cls_telegraph_news()
            
            # 宏观关键词库
            keywords = ["央行", "加息", "降息", "GDP", "CPI", "美联储", "战争", "突发", "重磅", "国务院", "A股", "港股", "外资", "汇率", "PMI"]
            
            for _, row in df.iterrows():
                content = str(row.get('content', ''))
                title = str(row.get('title', ''))
                
                # 清洗标题
                if not title or title == 'nan':
                    title = content[:30] + "..."
                
                # 去除 HTML 标签
                title = re.sub(r'<[^>]+>', '', title).strip()
                content = re.sub(r'<[^>]+>', '', content).strip()
                
                full_text = title + content
                
                # 关键词匹配
                if any(k in full_text for k in keywords):
                    news_list.append({
                        "title": title,
                        "source": "财联社",
                        "time": row.get('ctime', '')
                    })
                    
            return news_list[:5] # 只取前5条最重要的
            
        except Exception as e:
            logger.warning(f"宏观新闻获取失败: {e}")
            return [{"title": "宏观数据源暂时不可用，请关注市场盘面。", "source": "系统提示"}]

    def get_sector_news(self, keyword):
        """
        保留接口，具体抓取已下放至 news_analyst
        """
        return []
