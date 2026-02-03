import os
import json
import requests
import xml.etree.ElementTree as ET
from openai import OpenAI
from utils import retry, logger

class NewsAnalyst:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1") 
        self.model_name = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3") 
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url) if self.api_key else None

    @retry(retries=3)
    def fetch_news_titles(self, keyword):
        if "红利" in keyword: search_q = "中证红利 股息率"
        elif "白酒" in keyword: search_q = "白酒 茅台 批发价"
        else: search_q = keyword + " 行业分析"
        url = f"https://news.google.com/rss/search?q={search_q} when:2d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            return [item.find('title').text for item in root.findall('.//item')[:10]]
        except: return []

    def analyze_fund_v4(self, fund_name, tech_data, market_ctx, news_titles):
        return {} # V6.4中主要逻辑由Python接管，此函数可保留用于扩展
