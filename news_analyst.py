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
        
        # 保持我们测试成功的模型列表
        self.candidate_models = [
            'gemini-2.5-flash',
            'gemini-2.0-flash',
            'gemini-flash-latest',
            'gemini-pro-latest'
        ]
        self.model = None

    def _get_working_model(self):
        if self.model: return self.model
        for model_name in self.candidate_models:
            try:
                m = genai.GenerativeModel(model_name)
                return m
            except: continue
        return genai.GenerativeModel('gemini-flash-latest')

    @retry(retries=3)
    def fetch_news_titles(self, keyword):
        """获取新闻 (保持不变)"""
        if "红利" in keyword: search_q = "中证红利 基金"
        elif "白酒" in keyword: search_q = "白酒板块 茅台"
        elif "科技" in keyword: search_q = "恒生科技 港股"
        else: search_q = keyword + " 基金"

        url = f"https://news.google.com/rss/search?q={search_q} when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            titles = [item.find('title').text for item in root.findall('.//item')[:10]] # 取前10条
            return titles
        except Exception as e:
            logger.warning(f"新闻抓取失败: {e}")
            return []

    @retry(retries=2)
    def deep_analysis(self, fund_name, keyword, titles, market_context, tech_indicator):
        """
        【核心升级】深度逻辑推演
        """
        if not titles:
            return {"advice": "观望", "logic": "无新闻数据", "risk": "未知"}

        if not self.model: self.model = self._get_working_model()

        news_text = "\n".join([f"- {t}" for t in titles])
        
        # 顶级投资者 Prompt
        prompt = f"""
        你是一位管理百亿资金的顶级基金经理。现在需要对标的【{fund_name}】进行投资决策。
        
        【市场环境 (Macro)】
        - 北向资金(外资): {market_context['north_label']} ({market_context['north_money']}亿)
        - 今日主力资金流向Top板块: {', '.join(market_context['top_sectors'])}
        
        【技术面信号 (Technical)】
        - RSI指标: {tech_indicator['rsi']:.1f} ({'超卖' if tech_indicator['rsi']<35 else '超买' if tech_indicator['rsi']>70 else '中性'})
        - 趋势状态: {tech_indicator['price_position']} (相对于20日均线)
        
        【最新消息面 (News)】
        {news_text}
        
        请进行深度的逻辑推演，思考过程如下：
        1. **宏观与资金面**：全市场环境是否支持该板块上涨？主力资金是否在流入该板块？
        2. **基本面与消息**：新闻是实质性利好还是噪音？
        3. **博弈分析**：如果现在买入，胜率和赔率如何？
        
        请严格输出为 JSON 格式：
        {{
            "thesis": "一句话核心投资逻辑（如：宏观承压但板块超跌，博弈反弹）",
            "pros": "利多因素（简练）",
            "cons": "利空因素（简练）",
            "action_advice": "买入 / 卖出 / 观望 / 强力买入",
            "suggested_position": "仓位建议 (0-100%)",
            "risk_warning": "主要风险点"
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"AI深度分析失败: {e}")
            return {"thesis": "AI思考掉线", "action_advice": "观望", "risk_warning": "API Error"}
