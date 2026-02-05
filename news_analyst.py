import requests
import json
import os
import re
import time
import akshare as ak
from datetime import datetime
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

    @retry(retries=2, delay=2)
    def fetch_news_titles(self, keyword):
        if not keyword: return []
        news_list = []
        try:
            df = ak.stock_news_em(symbol="要闻")
            keys = keyword.split()
            for _, row in df.iterrows():
                title = str(row.get('title', ''))
                if any(k in title for k in keys):
                    news_list.append(f"[{row.get('public_time','')[-5:]}] {title}")
            if not news_list:
                return [f"近期无'{keyword}'直接相关资讯，需参考宏观大势。"]
            return news_list[:5] 
        except Exception as e:
            logger.warning(f"行业新闻抓取失败 {keyword}: {e}")
            return ["数据源暂时不可用"]

    def _clean_json(self, text):
        try:
            match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
            if match: return match.group(1)
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match: return match.group(0)
            return text
        except: return text

    @retry(retries=2, delay=2)
    def analyze_fund_v4(self, fund_name, tech_indicators, macro_summary, sector_news):
        score = tech_indicators.get('quant_score', 50)
        trend = tech_indicators.get('trend_weekly', '无趋势')
        valuation = tech_indicators.get('valuation_desc', '未知')
        obv_slope = tech_indicators.get('flow', {}).get('obv_slope', 0)
        
        money_flow = "主力抢筹" if obv_slope > 1.0 else ("主力出货" if obv_slope < -1.0 else "散户博弈")
        vol_ratio = tech_indicators.get('risk_factors', {}).get('vol_ratio', 1.0)
        
        if vol_ratio < 0.6: volume_status = "流动性枯竭(极度缩量)"
        elif vol_ratio < 0.8: volume_status = "缩量惜售"
        elif vol_ratio > 2.0: volume_status = "放量分歧"
        else: volume_status = "量能健康"

        prompt = f"""
        你现在是【玄铁基金投委会】的会议记录员。我们要对标的【{fund_name}】进行一场专业的投资辩论。

        【会议背景】
        - 宏观环境: {macro_summary[:200]}
        - 行业情报: {str(sector_news)[:500]}
        - **核心硬数据**: [评分:{score}] [估值:{valuation}] [资金:{money_flow}] [量能:{volume_status}] [趋势:{trend}]

        请模拟以下三位资深委员的发言。注意：**不要说废话，要像华尔街交易员一样直接、犀利、针锋相对。**

        ---
        **1. 🦊 CGO (首席增长官 - 动量猎手)**
        *人设核心*: 畏惧踏空 (FOMO)，信仰趋势。
        *思维逻辑*: "强者恒强"。如果资金在流入，哪怕估值贵也要上。
        *任务*: 挖掘上涨逻辑。如果 {fund_name} 在上涨但缩量，解释为"主力锁仓"。

        **2. 🐻 CRO (首席风控官 - 怀疑论者)**
        *人设核心*: 畏惧亏损，信仰均值回归。
        *思维逻辑*: "所有通过杠杆堆出来的繁荣都是泡沫"。
        *任务*: 泼冷水。如果 {fund_name} 在上涨但缩量，必须解释为"诱多，无承接"。重点攻击"背离"和"宏观压制"。

        **3. ⚖️ 轮值主席 (Chairman - 绝对理性)**
        *人设核心*: 权重分析师。
        *思维逻辑*: "多空都有理，但我只看赔率(Odds)"。
        *任务*: 
          - 判定 CGO 和 CRO 谁在"情绪化"，谁在"讲事实"。
          - **必须结合【硬数据】做最终裁决**。例如：CGO喊涨，但OBV显示主力出货，你必须判CGO败诉。
          - 给出战术修正分 (-30 ~ +30)。

        ---
        **输出要求 (JSON格式)**:
        {{
            "bull_view": "CGO: 极简犀利的看多理由 (30字内)",
            "bear_view": "CRO: 一针见血的风险警示 (30字内)",
            "chairman_conclusion": "主席: 综合裁决，说明采纳哪方观点的理由 (50字内)",
            "adjustment": 整数数值,
            "risk_alert": "无" 或 "具体的重大风险(如顶背离/流动性陷阱)"
        }}
        """

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4, 
            "max_tokens": 1000
        }
        
        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=90)
            if response.status_code != 200: return self._fallback_result()
            data = json.loads(self._clean_json(response.json()['choices'][0]['message']['content']))
            return {
                "bull_say": data.get("bull_view", "..."),
                "bear_say": data.get("bear_view", "..."),
                "comment": data.get("chairman_conclusion", "需人工介入"),
                "adjustment": int(data.get("adjustment", 0)),
                "risk_alert": data.get("risk_alert", "无")
            }
        except Exception as e:
            logger.error(f"投委会崩溃 {fund_name}: {e}")
            return self._fallback_result()

    def _fallback_result(self):
        return {"bull_say": "数据缺失", "bear_say": "风险未知", "comment": "连接中断，维持原判", "adjustment": 0, "risk_alert": "API Error"}

    # --- 2. CIO 战略审计 ---
    @retry(retries=2, delay=2)
    def review_report(self, report_text):
        prompt = f"""
        你是【玄铁量化】的 **CIO (首席投资官)**。你以**严厉、风控至上**著称。
        请对以下投委会决策汇总进行【战略审计】，输出 HTML 简报 (不要 Markdown)：

        【汇总】{report_text}

        内容要求：
        1. **宏观定调**: 明确当前是主动去库/补库？核心矛盾是什么？
        2. **双轨审计**: 批评或表扬底仓(红利/300)和卫星仓(科技)的决策。
        3. **最终指令**: 给出总仓位建议(0-100%)。

        输出模板：
        <p><b>宏观定调：</b>...</p>
        <p><b>双轨审计：</b>...</p>
        <p><b>CIO指令：</b>...</p>
        """
        return self._call_llm_text(prompt, "CIO 战略审计")

    # --- 3. 玄铁先生复盘 ---
    @retry(retries=2, delay=2)
    def advisor_review(self, report_text, macro_str):
        prompt = f"""
        你是 **【玄铁先生】**，一位量化宗师，信奉 **"重剑无锋"**。
        请写一段带有**武侠哲理**的【场外实战复盘】 (HTML格式)：

        【宏观】{macro_str}
        【决议】{report_text}

        1. **【势·验证】**: 分析主力意图(诱多/吸筹)。
        2. **【术·底仓】**: 点评防御资产。
        3. **【断·进攻】**: 点评进攻资产。

        输出模板：
        <h4>【势·验证】</h4><p>...</p>
        <h4>【术·底仓】</h4><p>...</p>
        <h4>【断·进攻】</h4><p>...</p>
        """
        return self._call_llm_text(prompt, "玄铁先生复盘")

    def _call_llm_text(self, prompt, task_name):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 1500
        }
        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=90)
            if response.status_code == 200:
                raw_text = response.json()['choices'][0]['message']['content']
                clean_text = raw_text.replace("```html", "").replace("```", "").strip()
                return clean_text
            return f"{task_name} 生成失败: API Error"
        except Exception as e:
            logger.error(f"{task_name} 失败: {e}")
            return f"{task_name} 暂时缺席 (网络波动)"
