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
        self.model = os.getenv("LLM_MODEL", "gpt-3.5-turbo") # 建议使用 GPT-4 或 Claude-3.5 以获得最佳人设体验
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    @retry(retries=2, delay=2)
    def fetch_news_titles(self, keyword):
        """行业新闻抓取"""
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

    # =========================================================================
    # 角色 1: 投委会 (The Investment Committee)
    # 职责: 微观博弈，针对具体标的的短线厮杀
    # =========================================================================
    @retry(retries=2, delay=2)
    def analyze_fund_v4(self, fund_name, tech_indicators, macro_summary, sector_news):
        # 1. 提取硬数据
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

        # 2. 深度人设 Prompt
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
            "temperature": 0.4, # 保持一定的专业严谨度
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

    # =========================================================================
    # 角色 2: CIO (Chief Investment Officer)
    # 职责: 战略审计，管理总风险敞口，防止局部最优导致全局崩盘
    # =========================================================================
    @retry(retries=2, delay=2)
    def review_report(self, report_text):
        """
        CIO 视角：战略审计与压力测试
        """
        prompt = f"""
        你是【玄铁量化】的 **CIO (首席投资官)**。你是一位久经沙场的机构操盘手，**以严厉、风控至上、大局观著称**。
        你现在面对的是各板块投委会提交上来的“散乱决策”，你需要将它们整合成一个有逻辑的投资组合。

        【投委会决策汇总】
        {report_text}

        请进行 **【战略审计 (Strategic Audit)】**，输出一份 HTML 简报 (不要 Markdown)：

        1.  **宏观定调 (The Macro Regime)**:
            - 不要复述新闻。请告诉我，现在的市场属于什么阶段？
            - 选项：*主动去库期(暴跌)*、*被动去库期(阴跌)*、*主动补库期(普涨)*、*被动补库期(滞涨)*。
            - 明确当前的核心矛盾（如：强预期 vs 弱现实）。

        2.  **双轨压力测试 (Stress Test)**:
            - **底仓审计** (红利/300)：投委会是否在下跌趋势中盲目抄底？如果是，请严厉批评并建议停止加仓。
            - **卫星审计** (科技/传媒)：投委会是否在缩量反弹中盲目追高？如果是，请提示“减仓兑现”。

        3.  **最终指令 (Final Mandate)**:
            - **点名表扬**：哪个板块的决策最符合当前宏观逻辑？
            - **点名批评**：哪个板块的决策在裸露风险敞口？
            - **总仓位控制**：基于当前风险，给出一个 0-100% 的建议仓位。

        **风格要求**：专业、冷峻、不带感情色彩。你不是来交朋友的，你是来管理风险的。
        
        输出模板：
        <p><b>宏观定调：</b>...</p>
        <p><b>双轨审计：</b>...</p>
        <p><b>CIO指令：</b>...</p>
        """
        return self._call_llm_text(prompt, "CIO 战略审计")

    # =========================================================================
    # 角色 3: 玄铁先生 (The Sage / The Master)
    # 职责: 哲学复盘，透过量价看人性，传授"重剑无锋"的道
    # =========================================================================
    @retry(retries=2, delay=2)
    def advisor_review(self, report_text, macro_str):
        """
        玄铁先生视角：量价心理学与投资之道
        """
        prompt = f"""
        你是 **【玄铁先生】**。你不是分析师，你是一位隐居的 **量化宗师**。
        你的投资哲学是 **"重剑无锋，大巧不工"** —— 摒弃花哨的预测，只跟随笨拙的趋势。
        你擅长通过 **成交量 (Volume)** 和 **价格形态 (Pattern)** 来洞察市场背后的 **群体心理 (Crowd Psychology)**。

        【宏观面】{macro_str}
        【决议表】{report_text}

        请写一段 **【场外实战复盘】**，严格遵循以下三段式 (HTML格式)：

        **1. 【势·验证】 (The Trend & Psychology)**
           - 此时此刻，市场的主流情绪是什么？（恐慌？贪婪？麻木？）
           - 结合宏观，指出主力资金是在“诱多出货”还是在“借利空吸筹”？
           - *金句要求*：用一句富有哲理的话总结当下的势。

        **2. 【术·底仓】 (The Shield)**
           - 点评防御性资产（红利/300）。
           - 强调：底仓不是为了赚钱，是为了**活下来**。如果底仓都在亏，说明系统性风险已至，必须空仓。

        **3. 【断·进攻】 (The Sword)**
           - 点评进攻性资产（科技/成长）。
           - 强调：**"不见兔子不撒鹰"**。如果没有放量突破，一切反弹都是耍流氓。
           - 告诫：如果技术指标（如RSI）过热，必须收剑入鞘。

        **风格要求**：
        - 语言要有“江湖气”但又不失专业。
        - 多用比喻（如：镰刀、韭菜、迷雾、深渊）。
        - 站在上帝视角，俯视市场的芸芸众生。

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
            "temperature": 0.5, # 适度创造性
            "max_tokens": 1500
        }
        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=90)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return f"{task_name} 生成失败: API Error"
        except Exception as e:
            logger.error(f"{task_name} 失败: {e}")
            return f"{task_name} 暂时缺席 (网络波动)"
