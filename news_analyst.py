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
        
        # 【最终修复】根据你的日志，精准填入可用的模型
        self.candidate_models = [
            'gemini-2.5-flash',       # 日志里显示的首选，2026年的主流
            'gemini-2.0-flash',       # 备选
            'gemini-flash-latest',    # 通用别名 (永远指向最新版)
            'gemini-pro-latest'       # 保底
        ]
        self.model = None

    def _get_working_model(self):
        """尝试找到一个可用的模型"""
        if self.model: return self.model
        
        for model_name in self.candidate_models:
            try:
                # 尝试初始化
                m = genai.GenerativeModel(model_name)
                logger.info(f"✅ 成功加载模型: {model_name}")
                return m
            except Exception:
                continue
        
        # 如果都失败了，盲猜一个
        logger.warning("备选模型都失败，尝试使用 gemini-flash-latest")
        return genai.GenerativeModel('gemini-flash-latest')

    @retry(retries=3)
    def fetch_news_titles(self, keyword):
        """通过 Google News RSS 获取新闻"""
        if "红利" in keyword: search_q = "中证红利 基金"
        elif "白酒" in keyword: search_q = "白酒板块 茅台"
        elif "科技" in keyword: search_q = "恒生科技 港股"
        else: search_q = keyword + " 基金"

        url = f"https://news.google.com/rss/search?q={search_q} when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
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

        # 懒加载模型
        if not self.model:
            self.model = self._get_working_model()

        news_text = "\n".join([f"- {t}" for t in titles])
        prompt = f"""
        你是一个理性的基金经理。请阅读下面关于“{keyword}”的新闻标题：
        {news_text}
        请直接回答两点（必须严格按照JSON格式返回）：
        1. score: 0到10的整数（0利空，5中性，10利好）。
        2. summary: 一句话总结利好/利空原因（20字以内）。
        格式示例：{{"score": 6, "summary": "消费回暖预期增强"}}
        """
        
        try:
            response = self.model.generate_content(prompt)
            text = response.text.replace('```json', '').replace('```', '').strip()
            result = json.loads(text)
            return int(result.get('score', 5)), result.get('summary', 'AI未提供总结')
        
        except Exception as e:
            logger.error(f"Gemini 调用失败: {e}")
            return 5, "AI分析异常，默认中性"
