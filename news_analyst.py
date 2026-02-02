import requests
import xml.etree.ElementTree as ET
import google.generativeai as genai
import os
import json
from utils import retry, logger

class NewsAnalyst:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("未设置 GEMINI_API_KEY")
        
        genai.configure(api_key=api_key)
        
        # 【关键修改】 按照指示，改回最稳的 'gemini-pro'
        # 这能解决 404 models/gemini-1.5-flash not found 的报错
        self.model = genai.GenerativeModel('gemini-pro')

    @retry(retries=3)
    def fetch_news_titles(self, keyword):
        """通过 Google News RSS 获取新闻"""
        # 增加关键词丰富度，提高命中率
        if "红利" in keyword: search_q = "中证红利 基金"
        elif "白酒" in keyword: search_q = "白酒板块 茅台"
        elif "科技" in keyword: search_q = "恒生科技 港股"
        else: search_q = keyword + " 基金"

        # 使用 RSS 搜索最近 24 小时 (when:1d)
        url = f"https://news.google.com/rss/search?q={search_q} when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            # 解析 XML，只取前 8 条
            titles = [item.find('title').text for item in root.findall('.//item')[:8]]
            logger.info(f"获取到 [{search_q}] 相关新闻 {len(titles)} 条")
            return titles
        except Exception as e:
            logger.warning(f"新闻抓取失败: {e}")
            return []

    @retry(retries=2)
    def analyze_sentiment(self, keyword, titles):
        """调用 Gemini 分析情绪"""
        if not titles:
            return 5, "无足够新闻数据"

        news_text = "\n".join([f"- {t}" for t in titles])
        
        # 简化 Prompt，gemini-pro 对 JSON 的遵循度稍弱，所以Prompt要更直接
        prompt = f"""
        你是一个理性的基金经理。请阅读下面关于“{keyword}”的新闻标题：
        {news_text}
        
        请直接回答两点（必须严格按照JSON格式返回）：
        1. score: 0到10的整数（0利空，5中性，10利好）。
        2. summary: 一句话总结利好/利空原因（20字以内）。
        
        JSON格式示例：
        {{
            "score": 6,
            "summary": "消费回暖预期增强，但短期有回调压力。"
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            # 清洗 markdown 标记 (gemini-pro 经常喜欢加 ```json)
            text = response.text.replace('```json', '').replace('```', '').strip()
            result = json.loads(text)
            return int(result.get('score', 5)), result.get('summary', 'AI未提供总结')
        except Exception as e:
            # 如果解析失败，打印原始返回以便调试
            raw_text = response.text if 'response' in locals() else 'N/A'
            logger.error(f"Gemini 解析失败: {e} | 原始返回: {raw_text}")
            return 5, "AI分析异常，默认中性"
