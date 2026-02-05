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
            junk_words = ["汇总", "集锦", "收评"]
            
            for _, row in df.iterrows():
                title = str(row.get('title', ''))
                # 过滤垃圾词
                if any(jw in title for jw in junk_words): continue
                
                if any(k in title for k in keys):
                    # 格式化: [时间] 标题
                    time_str = str(row.get('public_time',''))[-5:]
                    news_list.append(f"[{time_str}] {title}")
            
            if not news_list:
                return [f"近期无'{keyword}'直接资讯，参考宏观面。"]
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
        # 1. 提取硬数据
        score = tech_indicators.get('quant_score', 50)
        trend = tech_indicators.get('trend_weekly', '无趋势')
        valuation = tech_indicators.get('valuation_desc', '未知')
        obv_slope = tech_indicators.get('flow', {}).get('obv_slope', 0)
        
        money_flow = "资金抢筹" if obv_slope > 1.0 else ("资金出逃" if obv_slope < -1.0 else "存量博弈")
        vol_ratio = tech_indicators.get('risk_factors', {}).get('vol_ratio', 1.0)
        
        if vol_ratio < 0.6: volume_status = "流动性枯竭"
        elif vol_ratio < 0.8: volume_status = "缩量"
        elif vol_ratio > 2.0: volume_status = "放量分歧"
        else: volume_status = "温和"

        prompt = f"""
        你现在是【玄铁基金投委会】的会议记录员。对标的【{fund_name}】进行投资辩论。

        【硬数据】[评分:{score}] [估值:{valuation}] [资金:{money_flow}] [量能:{volume_status}] [趋势:{trend}]
        【宏观】{macro_summary[:200]}
        【行业新闻】{str(sector_news)[:500]}

        请模拟以下三位委员的专业发言 (华尔街风格，拒绝废话)：

        1. 🦊 CGO (增长官): 动量交易者。信仰"强者恒强"，寻找上涨催化剂。
        2. 🐻 CRO (风控官): 怀疑论者。信仰"均值回归"，警惕所有背离和泡沫。
        3. ⚖️ 主席 (决策者): 绝对理性。基于【硬数据】和【赔率】做最终裁决。

        **输出要求 (JSON)**:
        {{
            "bull_view": "CGO: 简练的看多逻辑 (30字内)",
            "bear_view": "CRO: 简练的风险警示 (30字内)",
            "chairman_conclusion": "主席: 最终裁决及理由 (50字内)",
            "adjustment": 整数数值,
            "risk_alert": "无" 或 "风险点"
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
            if response.status_code != 200: return self._fallback_result(sector_news)
            data = json.loads(self._clean_json(response.json()['choices'][0]['message']['content']))
            return {
                "bull_say": data.get("bull_view", "..."),
                "bear_say": data.get("bear_view", "..."),
                "comment": data.get("chairman_conclusion", "需人工介入"),
                "adjustment": int(data.get("adjustment", 0)),
                "risk_alert": data.get("risk_alert", "无"),
                "used_news": sector_news # [新增] 返回所使用的新闻，用于前端展示
            }
        except Exception as e:
            logger.error(f"投委会崩溃 {fund_name}: {e}")
            return self._fallback_result(sector_news)

    def _fallback_result(self, news):
        return {"bull_say": "数据缺失", "bear_say": "风险未知", "comment": "连接中断", "adjustment": 0, "risk_alert": "API Error", "used_news": news}

    # --- 2. CIO 战略审计 ---
    @retry(retries=2, delay=2)
    def review_report(self, report_text):
        prompt = f"""
        你是【玄铁量化】的 **CIO (首席投资官)**。你以**严厉、风控至上**著称。
        请对以下决策汇总进行【战略审计】，输出 HTML 简报 (不要 Markdown)：

        【汇总】{report_text}

        内容要求：
        1. **宏观定调**: 明确当前周期（衰退/复苏/过热/滞涨）及核心矛盾。
        2. **双轨审计**: 
           - 底仓(红利/300): 是否稳健？
           - 卫星仓(科技/周期): 是否冒进？
        3. **最终指令**: 给出总仓位建议(0-100%)。

        输出模板：
        <div class="cio-section">
            <h3 style="border-left: 4px solid #d32f2f; padding-left: 10px; color: #e0e0e0;">宏观定调</h3>
            <p>...</p>
            <h3 style="border-left: 4px solid #d32f2f; padding-left: 10px; color: #e0e0e0;">双轨审计</h3>
            <p>...</p>
            <h3 style="border-left: 4px solid #d32f2f; padding-left: 10px; color: #e0e0e0;">CIO指令</h3>
            <p>...</p>
        </div>
        """
        return self._call_llm_text(prompt, "CIO 战略审计")

    # --- 3. 玄铁先生复盘 (人设重塑：去江湖气，存哲学气) ---
    @retry(retries=2, delay=2)
    def advisor_review(self, report_text, macro_str):
        prompt = f"""
        你是 **【玄铁先生】**。
        你是一位 **冷峻的市场哲学家** 和 **量化交易宗师**。
        你摒弃了所有花哨的预测，只相信 **"价格包容一切"** 和 **"群体心理博弈"**。
        你的语言风格：**深刻、冷静、直击本质**。不要使用"江湖"、"武侠"、"剑气"等词汇。用金融哲学和数学逻辑说话。

        【宏观】{macro_str}
        【决议】{report_text}

        请撰写【场外实战复盘】 (HTML格式)：

        1. **【势·验证】 (The Trend)**: 
           - 分析当下的市场阻力最小方向。
           - 此时是"贪婪"的好时机，还是"恐惧"的好时机？
           - 结合量能，判定主力是在吸筹还是派发。

        2. **【术·底仓】 (The Shield)**: 
           - 点评防御性资产。强调"活下来"比"赚得多"更重要。
           - 引用"反脆弱"或"安全边际"的概念。

        3. **【断·进攻】 (The Strike)**: 
           - 点评进攻性资产。
           - 强调"胜率"与"赔率"。如果没有非对称的收益机会，宁可不动。

        输出模板：
        <div class="advisor-section">
            <h4 style="color: #ffb74d;">【势·验证】</h4><p>...</p>
            <h4 style="color: #ffb74d;">【术·底仓】</h4><p>...</p>
            <h4 style="color: #ffb74d;">【断·进攻】</h4><p>...</p>
        </div>
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
