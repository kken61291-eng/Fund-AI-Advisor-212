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
        # 优先使用环境变量中的模型，默认为 kimi (适合长文本分析)
        self.model = os.getenv("LLM_MODEL", "moonshot-v1-8k") 
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def fetch_news_titles(self, keyword):
        """
        占位函数，保持接口兼容性。
        实战数据流由 external scanner -> main.py -> analyze_fund_v4 传入
        """
        return [] 

    def _clean_json(self, text):
        """清洗 AI 返回的 JSON (去除 Markdown 和非 JSON 字符)"""
        try:
            # 1. 尝试提取代码块 ```json ... ```
            match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
            if match: return match.group(1)
            # 2. 尝试提取最外层 { ... }
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match: return match.group(0)
            return text
        except: return text

    @retry(retries=2, delay=2)
    def analyze_fund_v4(self, fund_name, tech_indicators, macro_summary, sector_news):
        """
        V14.1: 投委会辩论模式 (带核心投资哲学注入)
        """
        # --- 1. 数据预处理 (将硬指标翻译为 AI 可读语言) ---
        score = tech_indicators.get('quant_score', 50)
        trend = tech_indicators.get('trend_weekly', '无趋势')
        valuation = tech_indicators.get('valuation_desc', '未知')
        
        # 资金流向 (OBV)
        obv_slope = tech_indicators.get('flow', {}).get('obv_slope', 0)
        if obv_slope > 1.5: money_flow = "主力大幅抢筹"
        elif obv_slope > 0: money_flow = "温和流入"
        elif obv_slope < -1.5: money_flow = "主力坚决出货"
        else: money_flow = "资金流出"
        
        # 量能状态 (VR)
        vol_ratio = tech_indicators.get('risk_factors', {}).get('vol_ratio', 1.0)
        if vol_ratio < 0.6: volume_status = "极度缩量(没人玩)"
        elif vol_ratio < 0.8: volume_status = "缩量"
        elif vol_ratio > 2.0: volume_status = "放量滞涨(警惕)" if score < 40 else "放量上攻"
        else: volume_status = "量能正常"

        # --- 2. 构建核心 Prompt (注入灵魂) ---
        prompt = f"""
        你现在是【玄铁基金投委会】的会议记录员。我们需要对标的【{fund_name}】进行即时投资决策辩论。

        ### 📜 投委会最高宪章 (Core Philosophy)
        1. **重剑无锋**：我们不博短线运气，只吃周期和趋势的钱。
        2. **数据为王**：当【新闻情绪】与【硬数据】冲突时，无条件信任硬数据（估值/趋势/资金）。
        3. **厌恶风险**：主席的决策必须基于"生存第一"原则。宁可踏空，不可套牢。

        ### 📊 标的硬数据 (Fact Check)
        - **战术评分**: {score}分 (技术面基准)
        - **周期估值**: {valuation} (战略锚点)
        - **资金流向**: {money_flow} (OBV斜率)
        - **量能状态**: {volume_status} (VR量比)
        - **周线趋势**: {trend}

        ### 🌍 市场情报
        - 宏观环境: {macro_summary[:200]}
        - 行业舆情: {str(sector_news)[:500]}

        ### 🗣️ 请模拟以下三位委员的发言 (角色扮演)

        **1. 🦊 首席增长官 (CGO - The Bull):**
           - 性格：贪婪、激进、对利好极度敏感。
           - 任务：寻找做多理由。如果资金流入或估值低，请大声疾呼买入。
           - 话术风格："资金都在抢筹！" "这是历史性机遇！" "利空就是倒车接人！"

        **2. 🐻 首席风控官 (CRO - The Bear):**
           - 性格：多疑、悲观、专门泼冷水。
           - 任务：寻找做空理由。重点攻击"背离"、"缩量"和"旧闻炒作"。
           - 话术风格："这是典型的诱多！" "量能根本跟不上！" "估值太贵了，快跑！"

        **3. ⚖️ 投委会主席 (Chairman - The Judge):**
           - 性格：理智、客观、辩证、权重分析。
           - 任务：
             1. **听取辩论**：总结 CGO 和 CRO 的核心冲突点。
             2. **权重分析**：结合【硬数据】判断谁更有理。例如：CGO 喊涨，但硬数据由"资金流出"，你必须判 CGO 败诉。
             3. **最终裁决**：给出最终修正分 (-30 到 +30) 和一句话定调。

        ### 📤 输出要求
        必须返回严格的 JSON 格式 (不要包含 Markdown)：
        {{
            "bull_view": "CGO的激进观点(30字内)",
            "bear_view": "CRO的风险警示(30字内)",
            "chairman_conclusion": "主席的理智裁决(50字内，体现硬数据的权重)",
            "adjustment": 整数数值,
            "risk_alert": "如果有重大风险(如背离/极高估)请写明，否则填'无'"
        }}
        """

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3, # 低温以保持理智
            "max_tokens": 1000
        }
        
        try:
            # 发起请求
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=45 # 稍微延长超时，给 AI 思考时间
            )
            
            # 错误处理
            if response.status_code != 200:
                logger.error(f"AI API Error: {response.text}")
                return self._fallback_result()

            res_json = response.json()
            content = res_json['choices'][0]['message']['content']
            
            # 解析与清洗
            data = json.loads(self._clean_json(content))
            
            # 格式校验与返回
            return {
                "bull_say": data.get("bull_view", "观点模糊"),
                "bear_say": data.get("bear_view", "风险不明"),
                "comment": data.get("chairman_conclusion", "需人工介入"),
                "adjustment": int(data.get("adjustment", 0)),
                "risk_alert": data.get("risk_alert", "无")
            }

        except Exception as e:
            logger.error(f"投委会辩论崩溃 {fund_name}: {e}")
            return self._fallback_result()

    def _fallback_result(self):
        """降级方案"""
        return {
            "bull_say": "数据不足",
            "bear_say": "风险未知",
            "comment": "连接中断，维持技术面原判",
            "adjustment": 0,
            "risk_alert": "API Error"
        }

    def review_report(self, text):
        return "投委会会议纪要已归档。"
    
    def advisor_review(self, text, macro):
        return "投资顾问已审阅。"
