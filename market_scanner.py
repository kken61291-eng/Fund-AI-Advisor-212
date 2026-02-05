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
        获取宏观新闻 (财联社电报 - 新版接口)
        """
        news_list = []
        try:
            # [修复] 接口变更为 stock_telegraph_cls
            df = ak.stock_telegraph_cls()
            
            # 宏观关键词库
            keywords = ["央行", "加息", "降息", "GDP", "CPI", "美联储", "战争", "突发", "重磅", "国务院", "A股", "港股", "外资", "汇率", "PMI"]
            
            for _, row in df.iterrows():
                content = str(row.get('content', ''))
                title = str(row.get('title', ''))
                
                # 清洗标题
                if not title or title == 'nan':
                    title = content[:30] + "..."
                
                title = re.sub(r'<[^>]+>', '', title).strip()
                content = re.sub(r'<[^>]+>', '', content).strip()
                full_text = title + content
                
                if any(k in full_text for k in keywords):
                    news_list.append({
                        "title": title,
                        "source": "财联社",
                        "time": row.get('ctime', '')
                    })
                    
            return news_list[:5] 
            
        except Exception as e:
            logger.warning(f"宏观新闻获取失败: {e}")
            # 备用方案：尝试使用东方财富新闻
            try:
                df = ak.stock_news_em(symbol="要闻")
                if not df.empty:
                    return [{"title": row['title'], "source": "东财"} for _, row in df.head(3).iterrows()]
            except: pass
            
            return [{"title": "宏观数据源暂时不可用，请关注市场盘面。", "source": "系统提示"}]

    def get_sector_news(self, keyword):
        return []
