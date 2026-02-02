import requests
import xml.etree.ElementTree as ET
import google.generativeai as genai
import os
import json
import time
from utils import retry, logger

class NewsAnalyst:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("未设置 GEMINI_API_KEY，将使用备用情绪分析")
            self.model = None
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    @retry(retries=3)
    def fetch_news_titles(self, keyword):
        """通过 Google News RSS 获取相关板块新闻标题"""
        try:
            # URL 编码关键词
            import urllib.parse
            encoded_keyword = urllib.parse.quote(keyword)
            url = f"https://news.google.com/rss/search?q={encoded_keyword}+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            titles = []
            for item in root.findall('.//item')[:8]:  # 取前8条，减少API调用量
                title = item.find('title')
                if title is not None:
                    titles.append(title.text)
            
            logger.info(f"获取到 [{keyword}] 相关新闻 {len(titles)} 条")
            return titles
        except Exception as e:
            logger.error(f"获取新闻失败: {e}")
            return []

    def analyze_sentiment(self, keyword, titles):
        """调用 Gemini 分析情绪，失败时返回中性评分"""
        if not self.model or not titles:
            return 5, "未启用AI分析或暂无新闻"
        
        # 添加延时避免限流（免费版 Gemini 建议 1-2秒间隔）
        time.sleep(1.5)
        
        news_text = "\n".join([f"- {t}" for t in titles])
        
        prompt = f"""
        你是一位专业的基金经理。请阅读以下关于“{keyword}”板块的最新新闻标题：
        
        {news_text}
        
        任务：
        1. 分析这些新闻对该板块短期（1-3天）走势的情绪影响。
        2. 给出一个 0-10 的情绪打分（0为极度利空，5为中性，10为极度利好）。
        3. 用一句简短的“人话”总结，不超过30个字。
        
        请严格按照 JSON 格式返回，不要有任何其他文字：
        {{
            "score": <数字0-10>,
            "summary": "<总结文本>"
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            text = response.text.replace('```json', '').replace('```', '').strip()
            result = json.loads(text)
            
            # 验证返回格式
            score = float(result.get('score', 5))
            score = max(0, min(10, score))  # 限制在0-10之间
            summary = result.get('summary', '分析完成')
            
            return score, summary
            
        except Exception as e:
            logger.error(f"Gemini 解析失败: {e}，返回文本: {response.text if 'response' in locals() else 'N/A'}")
            return 5, "AI分析异常，默认中性"