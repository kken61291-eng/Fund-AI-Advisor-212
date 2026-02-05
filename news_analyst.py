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
        # 移除 when:2d，由 MarketScanner 统一负责宏观，这里只抓个股关联
        search_q = keyword + " 行业分析"
        if "红利" in keyword: search_q = "A股 红利指数 股息率"
        elif "美股" in keyword: search_q = "美联储 降息 纳斯达克 宏观"
        elif "半导体" in keyword: search_q = "半导体 周期 涨价"
        elif "黄金" in keyword: search_q = "黄金 避险 美元指数"
        
        url = f"https://news.google.com/rss/search?q={search_q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            return [item.find('title').text for item in root.findall('.//item')[:5]]
        except: return []

    def analyze_fund_v4(self, fund_name, tech, market_ctx, news):
        """
        V12.1 微观审计：引入布林带、量比、背离
        """
        if not self.client: return {"comment": "AI Offline", "risk_alert": "", "adjustment": 0}

        risk = tech.get('risk_factors', {'bollinger_pct_b': 0.5, 'vol_ratio': 1.0, 'divergence': '无'})

        tech_context = f"""
        [核心数据]
        - 基准分: {tech['quant_score']}
        - 趋势: 周线{tech['trend_weekly']}, MACD{tech['macd']['trend']}
        - 资金: OBV斜率 {tech['flow']['obv_slope']}
        
        [风控暗哨 - 这里的异常最致命]
        - 量比 (Vol Ratio): {risk['vol_ratio']} (0.8以下为缩量，2.0以上为放量)
        - 布林带位置 (%B): {risk['bollinger_pct_b']} (>1.0为突破上轨，<0.0为跌破下轨)
        - 顶背离信号: {risk['divergence']} (若为'顶背离'，请高度警惕)
        """

        prompt = f"""
        # Role: 资深风控官 (Risk Officer)
        # Task: 寻找量价与情绪的致命裂痕。
        
        # Context
        - 标的: {fund_name}
        - 宏观新闻: {str(market_ctx)}
        - 个股舆情: {str(news)}
        - 技术侦测: {tech_context}

        # 核心鉴谎法则 (Xuantie Logic)
        1. **缩量上涨 (最为致命)**: 如果价格涨了，但 量比<0.8 且 OBV流出，这是主力画图诱多，**必须重罚**。
        2. **高位力竭**: 如果 %B > 1.0 (突破上轨) 但出现了 顶背离，这是多头最后的疯狂，**建议止盈**。
        3. **恐慌错杀**: 如果 %B < 0.0 (跌破下轨) 且 量比放大 (恐慌盘涌出)，可能是黄金坑，**可以加分**。

        # Output JSON
        {{
            "comment": "80字深度洞察。重点点评量比和布林带状态。",
            "risk_alert": "20字致命风险 (如：缩量诱多/高位背离)。",
            "adjustment": (整数 -100 到 +50) 
        }}
        """

        try:
            res = self.client.chat.completions.create(model=self.model_name, messages=[{"role":"user","content":prompt}], response_format={"type":"json_object"}, temperature=0.4)
            data = json.loads(res.choices[0].message.content)
            if 'adjustment' not in data: data['adjustment'] = 0
            return data
        except Exception as e:
            logger.error(f"AI 分析错误: {e}")
            return {"comment": "AI服务异常", "risk_alert": "无", "adjustment": 0}

    def review_report(self, summary):
        # 保持 V11.12 的 CIO 逻辑
        if not self.client: return "<p>CIO Offline</p>"
        prompt = f"""
        # Role: CIO (首席投资官)
        # Strategy: Core(底仓) + Satellite(卫星)
        # Plan: {summary}
        # Task: 宏观一致性 + 仓位评估 + 最终裁决
        # Notice: 关注那些被标记为"缩量诱多"或"背离"的资产，必须无情砍仓。
        # Output HTML: <div class='cio-seal'>CIO APPROVED</div><h3>CIO 战略审计</h3><p><strong>宏观定调：</strong>...</p><p><strong>双轨评估：</strong>...</p><p class='warning'><strong>最终裁决：</strong>...</p>
        """
        try:
            res = self.client.chat.completions.create(model=self.model_name, messages=[{"role":"user","content":prompt}], temperature=0.6)
            return res.choices[0].message.content.strip().replace('```html', '').replace('```', '')
        except: return "CIO Audit Failed."

    def advisor_review(self, summary, market_ctx):
        # 保持 V11.12 的顾问逻辑
        if not self.client: return ""
        prompt = f"""
        # Role: 玄铁先生 (资产配置专家)
        # Context: {market_ctx} | Plan: {summary}
        # Task: 为场外基民提供独立验证。
        # Focus: 重点解读"量比"和"背离"。如果ETF在缩量上涨，明确警告场外基民别追。
        # Output HTML: <div class='advisor-title'>🗡️ 玄铁先生·场外实战复盘</div><p><strong>【势·验证】：</strong>...</p><p><strong>【术·底仓】：</strong>...</p><p><strong>【断·进攻】：</strong>...</p>
        """
        try:
            res = self.client.chat.completions.create(model=self.model_name, messages=[{"role":"user","content":prompt}], temperature=0.5)
            return res.choices[0].message.content.strip().replace('```html', '').replace('```', '')
        except: return "Advisor Offline."
