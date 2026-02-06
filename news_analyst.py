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

    def _format_short_time(self, time_str):
        try:
            dt = datetime.strptime(str(time_str), "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%m-%d %H:%M")
        except:
            s = str(time_str)
            if len(s) > 10: return s[5:16]
            return s

    @retry(retries=2, delay=2)
    def fetch_news_titles(self, keywords_str):
        """
        [V14.21] 关键词矩阵搜索 (OR Logic + Fallback)
        """
        if not keywords_str: return []
        
        keys = keywords_str.split()
        news_list = []
        fallback_list = [] 
        
        try:
            df = ak.stock_news_em(symbol="要闻")
            junk_words = ["汇总", "集锦", "收评", "早报", "公告", "提示"]
            
            for _, row in df.iterrows():
                title = str(row.get('title', ''))
                raw_time = str(row.get('public_time', ''))
                
                if any(jw in title for jw in junk_words): continue
                
                time_str = self._format_short_time(raw_time)
                item = f"[{time_str}] {title}"
                
                if len(fallback_list) < 3:
                    fallback_list.append(item)

                if any(k in title for k in keys):
                    news_list.append(item)
            
            if not news_list:
                return [f"[市场背景] {x}" for x in fallback_list]
            
            return news_list[:8] 
            
        except Exception as e:
            logger.warning(f"关键词搜索微瑕: {e}")
            return ["数据源波动，参考宏观面。"]

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
        
        money_flow = "资金抢筹" if obv_slope > 1.0 else ("资金出逃" if obv_slope < -1.0 else "存量博弈")
        vol_ratio = tech_indicators.get('risk_factors', {}).get('vol_ratio', 1.0)
        
        if vol_ratio < 0.6: volume_status = "流动性枯竭"
        elif vol_ratio < 0.8: volume_status = "缩量"
        elif vol_ratio > 2.0: volume_status = "放量分歧"
        else: volume_status = "温和"

        # [V14.25] 辩证思维 Prompt
        prompt = f"""
        你现在是【玄铁基金投委会】的决策中枢。请对标的【{fund_name}】进行严谨的辩证分析。

        【实盘硬数据】
        - 评分: {score} (基础技术分)
        - 估值: {valuation}
        - 资金: {money_flow} (OBV斜率: {obv_slope:.2f})
        - 量能: {volume_status} (VR: {vol_ratio})
        - 趋势: {trend}

        【自检索情报】
        - 宏观: {macro_summary[:600]}
        - 行业: {str(sector_news)[:600]}

        请运用【辩证唯物主义】思维，进行以下三方会谈：

        1. 🦊 CGO (增长官 - 正方): 
           - 任务: 结合"实盘数据"与"最新利好"，论证上涨的必然性。
           - 要求: 必须引用具体新闻或数据，拒绝空谈。

        2. 🐻 CRO (风控官 - 反方): 
           - 任务: 寻找逻辑漏洞。如果缩量，指出是"流动性枯竭"而非"惜售"。如果利好，指出是否"利好兑现"。
           - 要求: 必须客观，不能为了反对而反对（诡辩）。

        3. ⚖️ CIO (首席投资官 - 裁判): 
           - 任务: 提炼两人观点，进行【独立验证】。
           - 决策逻辑: 
             * 如果硬数据（如趋势DOWN）与CGO观点冲突，以硬数据为准。
             * 如果出现"背离"（如缩量上涨），必须扣分。
           - 最终输出: 
             * 给出【CIO策略修正分】(范围 -30 到 +30)。
             * 正分为加仓/看多，负分为减仓/避险。
             * 结论必须收敛，明确是攻是守。

        **输出要求 (JSON)**:
        {{
            "bull_view": "CGO: 基于[某数据/新闻]... (30字)",
            "bear_view": "CRO: 警惕[某风险]... (30字)",
            "chairman_conclusion": "CIO: [收敛结论]... (50字)",
            "adjustment": 整数数值,
            "risk_alert": "无" 或 "具体风险点"
        }}
        """

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3, # 低温确保逻辑严密，不胡说八道
            "max_tokens": 1000
        }
        
        try:
            logger.info(f"🧠 [AI思考中] 请求分析 {fund_name}...")
            response = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=90)
            
            if response.status_code != 200: 
                logger.error(f"API Error: {response.text}")
                return self._fallback_result(sector_news)
                
            raw_content = response.json()['choices'][0]['message']['content']
            
            # [V14.25] 打印 AI 原始回复，满足全日志需求
            logger.info(f"🤖 [AI原始回复 {fund_name}]:\n{raw_content}")
            
            data = json.loads(self._clean_json(raw_content))
            return {
                "bull_say": data.get("bull_view", "..."),
                "bear_say": data.get("bear_view", "..."),
                "comment": data.get("chairman_conclusion", "需人工介入"),
                "adjustment": int(data.get("adjustment", 0)),
                "risk_alert": data.get("risk_alert", "无"),
                "used_news": sector_news 
            }
        except Exception as e:
            logger.error(f"投委会崩溃 {fund_name}: {e}")
            return self._fallback_result(sector_news)

    def _fallback_result(self, news):
        return {"bull_say": "数据缺失", "bear_say": "风险未知", "comment": "连接中断", "adjustment": 0, "risk_alert": "API Error", "used_news": news}

    # --- CIO 战略审计 ---
    @retry(retries=2, delay=2)
    def review_report(self, report_text):
        prompt = f"""
        你是【玄铁量化】的 **CIO**。
        请对以下汇总进行【战略审计】，输出 HTML。
        
        【汇总】{report_text}

        输出模板：
        <div class="cio-section">
            <h3 style="border-left: 4px solid #d32f2f; padding-left: 10px;">宏观定调</h3>
            <p>...</p>
            <h3 style="border-left: 4px solid #d32f2f; padding-left: 10px;">双轨审计</h3>
            <p>...</p>
            <h3 style="border-left: 4px solid #d32f2f; padding-left: 10px;">CIO指令</h3>
            <p>...</p>
        </div>
        """
        return self._call_llm_text(prompt, "CIO 战略审计")

    # --- 玄铁先生复盘 ---
    @retry(retries=2, delay=2)
    def advisor_review(self, report_text, macro_str):
        prompt = f"""
        你是 **【玄铁先生】**，一位冷峻的市场哲学家。
        请写一段【场外实战复盘】 (HTML)。

        【宏观】{macro_str[:1500]} 
        【决议】{report_text}

        请透过现象看本质。输出：
        <div class="advisor-section">
            <h4 style="color: #ffd700;">【势·验证】</h4><p>...</p>
            <h4 style="color: #ffd700;">【术·底仓】</h4><p>...</p>
            <h4 style="color: #ffd700;">【断·进攻】</h4><p>...</p>
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
