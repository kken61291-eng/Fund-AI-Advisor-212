import akshare as ak
import requests
import re
from datetime import datetime
from utils import logger, retry

class MarketScanner:
    def __init__(self):
        pass

    @retry(retries=2, delay=2) # [修复] backoff_factor -> delay
    def get_macro_news(self):
        """
        获取宏观新闻 (财联社电报)
        """
        news_list = []
        try:
            # 接口: cls_telegraph_news (财联社电报)
            df = ak.cls_telegraph_news()
            
            # 过滤关键词
            keywords = ["央行", "加息", "降息", "GDP", "CPI", "美联储", "战争", "突发", "重磅", "国务院", "A股", "港股", "外资"]
            
            for _, row in df.iterrows():
                content = str(row.get('content', ''))
                title = str(row.get('title', ''))
                
                # 如果没有标题，用内容截取
                if not title or title == 'nan':
                    title = content[:30] + "..."
                
                full_text = title + content
                
                # 时间过滤 (只看最近24小时)
                # 财联社返回通常是实时，这里简单取前5条重要的
                
                if any(k in full_text for k in keywords):
                    # 简单的清洗
                    clean_title = re.sub(r'<[^>]+>', '', title).strip()
                    news_list.append({
                        "title": clean_title,
                        "source": "财联社",
                        "time": row.get('ctime', '')
                    })
                    
            return news_list[:5] # 只返回前5条最宏观的
            
        except Exception as e:
            logger.warning(f"宏观新闻获取失败: {e}")
            # 备用：返回静态提示，防止报错
            return [{"title": "宏观数据源暂时不可用，请关注市场盘面。", "source": "系统提示"}]

    def get_sector_news(self, keyword):
        """
        [保留接口] 获取特定板块新闻
        """
        return []
