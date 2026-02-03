import requests
import xml.etree.ElementTree as ET
import os
import json
import time
from openai import OpenAI
from utils import retry, logger

class NewsAnalyst:
    def __init__(self):
        # 从环境变量读取配置
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1") 
        self.model_name = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3") # 默认值作为防呆

        if not self.api_key:
            # 这是一个软报错，允许程序在没有 AI 的情况下继续运行（只出技术指标）
            logger.warning("⚠️ 未检测到 LLM_API_KEY，AI 分析功能将跳过")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            logger.info(f"✅ AI 客户端初始化成功 (模型: {self.model_name})")

    @retry(retries=3)
    def fetch_news_titles(self, keyword):
        """抓取新闻"""
        if "红利" in keyword: search_q = "中证红利 基金"
        elif "白酒" in keyword: search_q = "白酒板块 茅台"
        elif "纳斯达克" in keyword: search_q = "纳斯达克 美股"
        elif "黄金" in keyword: search_q = "黄金价格 金价"
        else: search_q = keyword + " 基金"

        url = f"https://news.google.com/rss/search?q={search_q} when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            # 获取前 6 条新闻，避免 Token 过长
            titles = [item.find('title').text for item in root.findall('.//item')[:6]]
            return titles
        except:
            return []

    def analyze_fund_v4(self, fund_name, tech_data, market_ctx, news_titles):
        """
        V4.0 分析引擎 (OpenAI 协议通用版)
        """
        if not self.client:
            return {"thesis": "未配置 API Key", "action_advice": "观望", "pros":"", "cons":""}

        if not tech_data:
            return {"thesis": "数据不足", "action_advice": "观望", "pros":"", "cons":""}

        news_text = "; ".join(news_titles) if news_titles else "无重大新闻"
        
        # 极简 Prompt
        prompt = f"""
        角色：资深量化交易员。标的：{fund_name}。
        
        【硬数据】
        1. 趋势: 日线{tech_data['trend_daily']} | 周线{tech_data['trend_weekly']}
        2. 动能: RSI={tech_data['rsi']} (超卖<35, 超买>70)
        3. 乖离: 偏离MA20 {tech_data['bias_20']}%
        
        【环境】
        市场: {market_ctx.get('north_label','未知')} ({market_ctx.get('north_money',0)}亿)
        新闻: {news_text}
        
        请输出 JSON (Strict JSON):
        {{
            "thesis": "一句话核心逻辑(20字内)",
            "pros": "利多因素(简练)",
            "cons": "利空因素(简练)",
            "action_advice": "买入/卖出/观望/强力买入",
            "risk_warning": "最大风险"
        }}
        """

        try:
            # 标准 OpenAI 调用格式
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful financial assistant. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}, # 强制 JSON (如果模型支持)
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            # 清洗可能存在的 markdown 符号
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {"thesis": "AI 接口报错", "action_advice": "观望", "pros": str(e)[:20], "cons":""}
