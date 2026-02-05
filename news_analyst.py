import requests
import json
import os
import re
import time
from utils import logger, retry

class NewsAnalyst:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def fetch_news_titles(self, keyword):
        """
        此处逻辑由 external scanner 处理，为保持接口兼容保留
        实战中数据通常由 main.py 传入
        """
        return [] 

    def _clean_json(self, text):
        """清洗 AI 返回的 JSON (去除 Markdown 标记)"""
        try:
            # 尝试提取 ```json ... ``` 中的内容
            match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
            if match: return match.group(1)
            # 尝试提取纯 { ... }
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match: return match.group(0)
            return text
        except: return text

    @retry(retries=2, delay=2)
    def analyze_fund_v4(self, fund_name, tech_indicators, macro_summary, sector_news):
        """
        V14.0: 投委会三方辩论模式 (Committee Debate Mode)
        """
        # 提取关键数据供 AI 辩论
        score = tech_indicators.get('quant_score', 50)
        trend = tech_indicators.get('trend_weekly', '无趋势')
        valuation = tech_indicators.get('valuation_desc', '未知')
        
        # 资金流向判断
        obv_slope = tech_indicators.get('flow', {}).get('obv_slope', 0)
        money_flow = "大幅流入" if obv_slope > 1 else ("流出" if obv_slope < 0 else "平稳")
        
        # 风险判断
        vol_ratio = tech_indicators.get('risk_factors', {}).get('vol_ratio', 1.0)
        volume_status = "严重缩量" if vol_ratio < 0.6 else ("放量" if vol_ratio > 1.5 else "正常")

        prompt = f"""
        你现在是【玄铁基金投委会】的会议记录员。我们需要对标的【{fund_name}】进行严肃的投资辩论。

        【会议背景】
        - 宏观环境: {macro_summary[:300]}
        - 行业舆情: {str(sector_news)[:600]}

        【标的硬数据】
        - 战术评分: {score}分 (技术面)
        - 估值定位: {valuation} (战略面)
        - 资金流向: {money_flow}
        - 量能状态: {volume_status}
        - 周线趋势: {trend}

        请模拟以下三位委员的发言（必须犀利、针锋相对）：

        1. 🦊 首席增长官 (CGO - 激进多头):
           - 贪婪视角。挖掘新闻中的利好，强调资金流入或低估值机会。
           - 对"缩量"解释为"惜售"，对"利空"解释为"落地"。
           
        2. 🐻 首席风控官 (CRO - 保守空头):
           - 恐惧视角。挖掘背离、估值泡沫、宏观风险。
           - 必须反驳 CGO。对"缩量"解释为"无承接"，对"利好"解释为"出货"。
           - 尤其警惕：{fund_name} 是否存在"量价背离"或"旧闻炒作"。

        3. ⚖️ 轮值主席 (Chairman - 理智仲裁):
           - 听取双方辩论，结合【硬数据】做最终裁决。
           - 给出对【战术评分】的修正值 (-30 到 +30)。
           - 给出最终操作建议（观望/买入/卖出/锁仓）。

        必须返回严格的 JSON 格式，不要包含任何 Markdown 格式：
        {{
            "bull_view": "CGO的发言(30字内)",
            "bear_view": "CRO的发言(30字内)",
            "chairman_conclusion": "主席的最终定调(50字内)",
            "adjustment": 整数数值,
            "risk_alert": "如果有重大风险请写明，否则填'无'"
        }}
        """

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4, # 稍微降低随机性，保证辩论逻辑严密
            "max_tokens": 800
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=40
            )
            res_json = response.json()
            
            # 兼容不同的 API 返回格式
            if 'choices' in res_json:
                content = res_json['choices'][0]['message']['content']
            else:
                logger.error(f"API 返回结构异常: {res_json}")
                return {}

            # 解析 JSON
            data = json.loads(self._clean_json(content))
            
            return {
                "bull_say": data.get("bull_view", "多头缺席"),
                "bear_say": data.get("bear_view", "空头缺席"),
                "comment": data.get("chairman_conclusion", "需人工复核"),
                "adjustment": int(data.get("adjustment", 0)),
                "risk_alert": data.get("risk_alert", "无")
            }

        except Exception as e:
            logger.error(f"投委会辩论失败 {fund_name}: {e}")
            # 降级返回，保证流程不卡死
            return {
                "bull_say": "数据不足",
                "bear_say": "风险未知",
                "comment": "AI 接口异常，维持技术面原判",
                "adjustment": 0,
                "risk_alert": "API Error"
            }

    def review_report(self, text):
        return "投委会会议纪要已归档。"
    
    def advisor_review(self, text, macro):
        return "投资顾问已审阅。"
