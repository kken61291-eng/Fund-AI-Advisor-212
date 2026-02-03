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
        """抓取谷歌新闻RSS"""
        # 关键词映射
        if "红利" in keyword: search_q = "A股 红利指数"
        elif "白酒" in keyword: search_q = "白酒 茅台 股价"
        elif "美股" in keyword: search_q = "美联储 纳斯达克"
        elif "港股" in keyword: search_q = "恒生科技指数 腾讯 美团"
        elif "医疗" in keyword: search_q = "医药集采 创新药"
        elif "黄金" in keyword: search_q = "黄金价格 美元指数"
        else: search_q = keyword + " 行情"

        url = f"https://news.google.com/rss/search?q={search_q} when:2d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            # 获取前5条
            titles = [item.find('title').text for item in root.findall('.//item')[:5]]
            return titles
        except:
            return []

    def analyze_fund_v4(self, fund_name, tech_data, market_ctx, news_titles):
        """
        V7.2 全量版：AI 深度点评
        """
        if not self.client:
            return {"comment": "AI 未配置", "risk_alert": ""}

        # 整理输入数据给 AI
        score = tech_data['quant_score']
        rsi = tech_data['rsi']
        bias = tech_data['bias_20']
        trend_w = tech_data['trend_weekly']
        news_str = "; ".join(news_titles[:3]) if news_titles else "无重大新闻"

        prompt = f"""
        # Role
        你是一席位管理百亿资金的量化基金经理。你的风格是：**犀利、简练、一针见血**。

        # Data
        - 标的: {fund_name}
        - 量化评分: {score}分 (0-100)
        - 技术面: 周线{trend_w}, RSI={rsi}, 乖离率={bias}%
        - 舆情: {news_str}
        - 宏观: {market_ctx.get('north_label')} {market_ctx.get('north_money')}

        # Task
        请根据量化评分和技术数据，写一段 30字以内的**投资短评**。
        - 如果分高(>80)：强调机会难得，建议贪婪。
        - 如果分低(<40)：强调风险，建议防守。
        - 如果分数中庸：强调观望或定投。
        - **必须引用一个具体的指标数值** (如RSI或乖离) 来支撑你的观点。

        # Output (JSON)
        {{
            "comment": "你的30字犀利点评",
            "risk_alert": "一句话风险提示 (如: '周线空头压制' 或 'RSI严重超买')"
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a professional fund manager. Output valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            content = response.choices[0].message.content
            # 清洗可能的 markdown 符号
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
        except Exception as e:
            logger.error(f"AI 分析失败: {e}")
            return {"comment": "AI 服务繁忙", "risk_alert": "数据波动风险"}
