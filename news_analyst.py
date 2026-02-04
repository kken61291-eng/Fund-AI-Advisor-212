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
        self.model_name = os.getenv("LLM_MODEL", "Pro/moonshotai/Kimi-K2.5") 
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url) if self.api_key else None

    @retry(retries=2)
    def fetch_news_titles(self, keyword):
        search_q = keyword + " 行业分析"
        if "红利" in keyword: search_q = "A股 红利指数 股息率"
        elif "美股" in keyword: search_q = "美联储 降息 纳斯达克 宏观"
        elif "半导体" in keyword: search_q = "半导体 周期 涨价"
        elif "黄金" in keyword: search_q = "黄金 避险 美元指数"
        
        url = f"https://news.google.com/rss/search?q={search_q} when:2d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            return [item.find('title').text for item in root.findall('.//item')[:5]]
        except: return []

    def analyze_fund_v4(self, fund_name, tech, market_ctx, news):
        # 保持 V11.6 的微观审计（自由裁量权）
        if not self.client: return {"comment": "AI Offline", "risk_alert": "", "adjustment": 0}

        tech_context = f"""
        - 量化基准分: {tech['quant_score']} (0-100)
        - 趋势信号: 周线{tech['trend_weekly']}, MACD{tech['macd']['trend']}
        - 资金信号: OBV斜率 {tech['flow']['obv_slope']}
        - 情绪信号: RSI {tech['rsi']}
        """

        prompt = f"""
        # Role: 资深风控官 (Risk Officer)
        # Context
        - 标的: {fund_name}
        - 宏观: {str(market_ctx)}
        - 技术: {tech_context}
        - 舆情: {str(news)}

        # Task: 逻辑审计
        寻找数据中的漏洞。回答：“当前的上涨（或下跌）逻辑是真实的，还是主力画出来的？”

        # Output JSON
        {{
            "comment": "80字以内的深度洞察。给出定性判断（诱多/洗盘/抢筹）。",
            "risk_alert": "20字以内最需要警惕的风险点。",
            "adjustment": (整数 -100 到 +50) 
        }}
        """

        try:
            res = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}, 
                temperature=0.4
            )
            data = json.loads(res.choices[0].message.content)
            if 'adjustment' not in data: data['adjustment'] = 0
            return data
        except Exception as e:
            logger.error(f"AI 分析错误: {e}")
            return {"comment": "AI服务异常", "risk_alert": "无", "adjustment": 0}

    def review_report(self, summary):
        # 保持 V11.6 的 CIO 辩证审计
        if not self.client: return "<p>CIO Offline</p>"
        
        prompt = f"""
        # Role: 首席投资官 (CIO)
        你掌管几十亿头寸。你深知市场非线性，只有盈亏比。
        
        # Strategy (双轨制)
        - **核心底仓 (Core)**: 黄金/红利/大盘。任务是**活着**，扛过周期。
        - **卫星进攻 (Satellite)**: 科技/券商。任务是**掠夺**，博取高收益。

        # Plan
        {summary}

        # Task
        1. **宏观一致性**：检查配置是否顺应大势。
        2. **仓位舒适度**：评估风险敞口是否过大。
        3. **最终裁决**：给出方向性微调。

        # Output HTML
        结构：
        <div class='cio-seal'>CIO APPROVED</div>
        <h3>CIO 战略审计</h3>
        <p><strong>宏观辩证：</strong>...</p>
        <p><strong>双轨评估：</strong>...</p>
        <p class='warning'><strong>最终裁决：</strong>...</p>
        """
        try:
            res = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6 
            )
            return res.choices[0].message.content.strip().replace('```html', '').replace('```', '')
        except: return "CIO Audit Failed."

    def advisor_review(self, summary, market_ctx):
        """
        V11.8: 玄铁先生 (Master Xuantie) - 专业重塑版
        人设：50年经验资产配置专家。
        风格：客观、冷峻、聚焦场外基金的执行层面。
        """
        if not self.client: return ""

        prompt = f"""
        # Role: 玄铁先生 (Master Xuantie)
        你是一位**50年经验的资产配置专家**。你的视角独立于CIO，你更关注**交易机制的摩擦成本**和**场外基金的实战胜率**。
        你不再闲聊，你只提供**专业、客观的第二意见**。

        # Context
        宏观环境: {market_ctx}
        CIO的ETF策略:
        {summary}

        # Task
        请基于**场外基金(Mutual Funds)**的特殊机制（T+1确认、赎回费、净值磨损），对整份报告进行**独立验证**。
        
        # Analysis Framework (玄铁三式)
        1. **【势·验证】(Market Validation)**:
           - 结合宏观和盘面，客观评价CIO的宏观定调是否准确。
           - 重点分析：当前的市场成交量能否支撑场外基金的“T+1”入场？（如果是缩量上涨，明确指出场外入场即被套的数学概率）。
        
        2. **【术·底仓】(Core Logic)**:
           - 针对红利/黄金/大盘。
           - 从“长期复利”角度分析。告诉用户：尽管CIO可能提示短期风险，但作为底仓，场外基金的持有成本决定了我们应该“多看少动”还是“波段操作”。

        3. **【断·进攻】(Satellite Execution)**:
           - 针对科技/券商。
           - 极其严厉的执行建议。如果趋势破坏，明确指出场外基金“净值更新滞后”带来的巨大风险，建议立即止损或观望，杜绝侥幸。

        # Output HTML (无markdown)
        请使用专业、干练的语言，不要用“老弟”、“茶馆”等江湖黑话。
        结构:
        <div class='advisor-title'>🗡️ 玄铁先生·场外实战复盘</div>
        <p><strong>【势·验证】：</strong>[客观分析市场胜率与赔率]</p>
        <p><strong>【术·底仓】：</strong>[针对红利/黄金的配置建议]</p>
        <p><strong>【断·进攻】：</strong>[针对科技/券商的执行纪律]</p>
        """
        try:
            res = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5 # 降低温度，确保回答冷静、专业
            )
            return res.choices[0].message.content.strip().replace('```html', '').replace('```', '')
        except: return "Advisor Offline."
