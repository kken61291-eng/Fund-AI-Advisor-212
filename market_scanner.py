import akshare as ak
import requests
import re
from datetime import datetime
from utils import logger, retry

class MarketScanner:
    def __init__(self):
        pass

    def _format_time(self, time_str):
        """统一时间格式为 MM-DD HH:MM"""
        try:
            # 尝试解析完整时间 YYYY-MM-DD HH:MM:SS
            dt = datetime.strptime(str(time_str), "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%m-%d %H:%M")
        except:
            s = str(time_str)
            if len(s) > 10: return s[5:16]
            return s

    @retry(retries=2, delay=2) 
    def get_macro_news(self):
        """
        获取全市场重磅新闻 (V14.18 稳健版 - 回退至要闻接口，保留天网逻辑)
        """
        news_list = []
        try:
            # [回退] 使用最稳定的要闻接口，避免 Attribute Error
            df = ak.stock_news_em(symbol="要闻")
            
            title_col = 'title'
            if 'title' not in df.columns:
                if '新闻标题' in df.columns: title_col = '新闻标题'
                elif '文章标题' in df.columns: title_col = '文章标题'
            
            time_col = 'public_time'
            if 'public_time' not in df.columns:
                if '发布时间' in df.columns: time_col = '发布时间'
                elif 'time' in df.columns: time_col = 'time'

            # V14.17 的天网关键词库
            keywords = [
                "中共中央", "政治局", "国务院", "发改委", "财政部", "国资委", "证监会", "央行", "外管局", "新华社",
                "加息", "降息", "降准", "LPR", "MLF", "逆回购", "社融", "M2", "信贷", "特别国债", "赤字率", "流动性",
                "GDP", "CPI", "PPI", "PMI", "非农", "失业率", "通胀", "零售", "出口", "汇率", "人民币",
                "印花税", "T+0", "停牌", "注册制", "退市", "做空", "融券", "量化限制", "市值管理", "分红", "回购",
                "汇金", "证金", "社保基金", "大基金", "北向", "外资", "增持", "举牌", "平准基金",
                "突发", "重磅", "立案", "调查", "违约", "破产", "战争", "制裁", "地缘", "暴雷"
            ]
            
            # 垃圾词过滤
            junk_words = ["汇总", "集锦", "回顾", "收评", "早报", "晚报", "盘前", "要闻精选", "公告一览", "涨停分析", "复盘"]

            for _, row in df.iterrows():
                title = str(row.get(title_col, ''))
                raw_time = str(row.get(time_col, ''))
                
                if not title or title == 'nan': continue
                if any(jw in title for jw in junk_words): continue
                
                clean_time = self._format_time(raw_time)
                
                if any(k in title for k in keywords):
                    news_list.append({
                        "title": title.strip(),
                        "source": "全球快讯",
                        "time": clean_time
                    })
            
            # 兜底补充
            if len(news_list) < 5:
                for _, row in df.iterrows():
                    title = str(row.get(title_col, ''))
                    raw_time = str(row.get(time_col, ''))
                    if any(jw in title for jw in junk_words): continue
                    if any(n['title'] == title for n in news_list): continue
                    
                    news_list.append({
                        "title": title.strip(), 
                        "source": "市场资讯", 
                        "time": self._format_time(raw_time)
                    })
                    if len(news_list) >= 10: break

            return news_list
            
        except Exception as e:
            logger.warning(f"宏观新闻获取微瑕: {e}")
            return [{"title": "数据源波动，关注盘面资金。", "source": "系统", "time": datetime.now().strftime("%m-%d %H:%M")}]

    def get_sector_news(self, keyword):
        return []
