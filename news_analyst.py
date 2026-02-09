import requests
import json
import os
import re
from datetime import datetime
from utils import logger, retry

class NewsAnalyst:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        
        # [V15.6 算力分层架构]
        # 战术执行层: DeepSeek-V3 (低延迟、结构化、严守纪律)
        self.model_tactical = "Pro/deepseek-ai/DeepSeek-V3"     
        
        # 战略思考层: DeepSeek-R1 (思维链、非线性推理、归因分析)
        self.model_strategic = "Pro/deepseek-ai/DeepSeek-R1" 

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.cls_headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.cls.cn/telegraph",
            "Origin": "https://www.cls.cn"
        }

    def _format_short_time(self, time_str):
        try:
            if str(time_str).isdigit():
                dt = datetime.fromtimestamp(int(time_str))
                return dt.strftime("%m-%d %H:%M")
            if len(str(time_str)) > 10:
                dt = datetime.strptime(str(time_str), "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%m-%d %H:%M")
            return str(time_str)
        except:
            return str(time_str)[:11]

    def _fetch_eastmoney_news(self):
        try:
            import akshare as ak
            df = ak.stock_news_em(symbol="要闻")
            raw_list = []
            for _, row in df.iterrows():
                title = str(row.get('title', ''))[:40]
                raw_list.append(f"[{str(row.get('public_time',''))[5:16]}] (东财) {title}")
            return raw_list[:5]
        except:
            return []

    def _fetch_cls_telegraph(self):
        raw_list = []
        url = "https://www.cls.cn/nodeapi/telegraphList"
        params = {"rn": 20, "sv": 7755}
        try:
            resp = requests.get(url, headers=self.cls_headers, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and "roll_data" in data["data"]:
                    for item in data["data"]["roll_data"]:
                        title = item.get("title", "")
                        content = item.get("content", "")
                        txt = title if title else content[:50]
                        time_str = self._format_short_time(item.get("ctime", 0))
                        raw_list.append(f"[{time_str}] (财社) {txt}")
        except Exception as e:
            logger.warning(f"财社源微瑕: {e}")
        return raw_list

    @retry(retries=2, delay=2)
    def fetch_news_titles(self, keywords_str):
        l1 = self._fetch_cls_telegraph()
        l2 = self._fetch_eastmoney_news()
        all_n = l1 + l2
        hits = []
        keys = keywords_str.split()
        seen = set()
        for n in all_n:
            clean_n = n.split(']')[-1].strip()
            if clean_n in seen: continue
            seen.add(clean_n)
            if any(k in n for k in keys):
                hits.append(n)
        return hits[:8] if hits else l1[:3]

    def _clean_json(self, text):
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            return match.group(0) if match else "{}"
        except: return "{}"

    @retry(retries=1, delay=2)
    def analyze_fund_v5(self, fund_name, tech, macro, news, risk):
        """
        战术层: V3 模型
        任务: CGO(进攻) -> CRO(风控) -> CIO(裁决) 闭环
        特点: 严格 JSON 输出，低温度(0.1)，无幻觉
        """
        # 数据解构
        fuse = risk['fuse_level']
        fuse_msg = risk['risk_msg']
        
        trend = tech.get('trend_weekly', '无趋势')
        rsi = tech.get('rsi', 50)
        macd = tech.get('macd', {})
        macd_str = f"Trend:{macd.get('trend','N/A')}, Hist:{macd.get('hist',0)}"
        vol_ratio = tech.get('risk_factors', {}).get('vol_ratio', 1.0)
        pct_b = tech.get('risk_factors', {}).get('bollinger_pct_b', 0.5)
        
        # 1. 构造 CGO 提示词 (V3-极速版)
        cgo_prompt = f"""
        【系统角色】
        你是玄铁量化基金的**CGO (动量策略分析师)**，专注右侧交易与Alpha挖掘。
        
        【输入数据】
        标的: {fund_name}
        技术因子:
        - 趋势: {trend}
        - RSI(14): {rsi}
        - MACD: {macd_str}
        - 成交量偏离(VR): {vol_ratio}
        - 布林位置: {pct_b}
        舆情因子: {str(news)[:400]}

        【分析框架】
        1. 趋势确认: 周线方向？均线排列？
        2. 动量质量: RSI是否处于40-70健康区间？
        3. 量能验证: 上涨是否放量？VR>1.2为确认，<0.8为警示
        4. 赔率测算: 目标位/止损位
        
        【纪律】
        - 若趋势强度弱(周线Down)，直接输出HOLD。
        - 禁止模糊表述，禁止情绪词汇。
        """

        # 2. 构造 CRO 提示词 (V3-硬约束版)
        cro_prompt = f"""
        【系统角色】
        你是玄铁量化基金的**CRO (风控合规官)**，负责左侧风险扫描。
        
        【风险因子】
        - 熔断等级: {fuse}级 (指令: {fuse_msg})
        - 技术背离: 价格与RSI/MACD是否背离？
        - 流动性: VR={vol_ratio} (VR<0.6为流动性枯竭)
        
        【压力测试框架】
        1. 熔断硬约束: 若等级>=2，自动触发Veto。
        2. 流动性折价: 冲击成本测算。
        3. 宏观错配: 当前环境是否支持该资产？
        
        【硬约束】
        - 必须证明"为什么现在不该做"。
        - 禁止与CGO妥协。
        """

        # 3. 构造 CIO 提示词 (V3-裁决版)
        cio_prompt = f"""
        【系统角色】
        你是玄铁量化基金的**CIO (投资总监)**。你接收CGO与CRO的观点，做出战术裁决。
        
        【决策矩阵】
        1. 胜率<40% 或 赔率<1:1.5 -> 否决
        2. 熔断等级>=2 -> 否决
        3. 胜率>60% 且 风险可控 -> 批准
        
        【输出格式-严格JSON】
        {{
            "bull_view": "CGO观点 (50字): 核心逻辑与赔率测算。",
            "bear_view": "CRO观点 (50字): 核心风险与熔断警示。",
            "chairman_conclusion": "CIO裁决 (80字): 最终战术定性。包含：决策(买/卖/观望)、仓位建议、止损位。",
            "adjustment": 整数数值 (-30 到 +30)
        }}
        """

        # 合并 Prompt 给 V3 (利用 V3 的长窗口一次性处理，保证上下文连贯)
        final_prompt = f"{cgo_prompt}\n\n{cro_prompt}\n\n{cio_prompt}\n\n请模拟上述三位专家的思考过程，并直接输出最终的 JSON 结果。"
        
        payload = {
            "model": self.model_tactical, # V3
            "messages": [{"role": "user", "content": final_prompt}],
            "temperature": 0.2, # 低温，确保结构化和纪律性
            "max_tokens": 1000,
            "response_format": {"type": "json_object"}
        }
        
        try:
            resp = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=90)
            if resp.status_code != 200:
                logger.error(f"API Error: {resp.text[:100]}")
                raise Exception(f"API {resp.status_code}")
                
            data = resp.json()
            if isinstance(data, str): data = json.loads(data)
            content = data['choices'][0]['message']['content']
            return json.loads(self._clean_json(content))
        except Exception as e:
            logger.error(f"AI战术分析异常 {fund_name}: {e}")
            raise e

    @retry(retries=2, delay=5)
    def review_report(self, report_text):
        """
        战略层: R1 模型
        任务: 机构级市场复盘备忘录
        特点: 深度推理，高温度(0.4)，HTML输出
        """
        prompt = f"""
        【系统角色】
        你是玄铁量化基金的**CIO (投资总监)**，负责撰写机构级市场复盘备忘录。
        此报告将提交投委会，作为下一阶段风险预算与战略调整的依据。
        
        【输入数据】
        全市场交易汇总:
        {report_text}
        
        【深度分析要求 - 必须使用 DeepSeek-R1 思维链】
        1. 收益归因: 拆解Alpha来源，识别运气与能力。
        2. 风险归因: 风险主要来自系统性暴露还是特异性风险？
        3. 策略失效检测: 当前市场regime是否导致策略暂时失效？
        
        【输出格式-HTML】
        <div class="cio-memo">
            <h3 style="border-left: 4px solid #1a237e; padding-left: 10px;">宏观环境审视</h3>
            <p>流动性评估与风险偏好审计（100字）。</p>
            
            <h3 style="border-left: 4px solid #1a237e; padding-left: 10px;">收益与风险归因</h3>
            <p>基于数据的归因分析与异常点解释（100字）。</p>
            
            <h3 style="border-left: 4px solid #d32f2f; padding-left: 10px;">CIO战术指令</h3>
            <p>总仓位控制、风险敞口调整与明日重点监控阈值（80字）。</p>
        </div>
        """
        
        payload = {
            "model": self.model_strategic, # R1
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 3000,
            "temperature": 0.4 # 适度创造性，允许深度推理
        }
        try:
            resp = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=120)
            data = resp.json()
            if isinstance(data, str): data = json.loads(data)
            content = data['choices'][0]['message']['content']
            clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            return self._clean_html(clean_content)
        except:
            return "<p>CIO 正在进行深度战略审计...</p>"

    @retry(retries=2, delay=5)
    def advisor_review(self, report_text, macro_str):
        """
        战略层: R1 模型
        任务: 首席宏观策略师报告
        特点: 周期定位，非线性推理
        """
        prompt = f"""
        【系统角色】
        你是玄铁量化基金的**首席宏观策略师**。
        你使用DeepSeek-R1的深度推理能力，识别非线性关系与预期差。
        
        【输入数据】
        宏观背景: {macro_str[:400]}
        市场数据: {report_text}
        
        【推理要求 - 必须使用 DeepSeek-R1 思维链】
        1. 周期定位: 当前处于三周期（库存/信用/货币）的什么阶段？
        2. 预期差识别: 市场当前price in了什么宏观假设？
        3. 策略映射: 基于周期位置，最优配置策略是什么？
        
        【输出格式-HTML结构化】
        <div class="macro-report">
            <h4 style="color: #ffd700;">【势·周期定位】</h4>
            <p>当前周期阶段判定与历史可比阶段对标（100字）。</p>
            
            <h4 style="color: #ffd700;">【术·预期差分析】</h4>
            <p>市场隐含假设与潜在修正风险点（100字）。</p>
            
            <h4 style="color: #ffd700;">【断·战略配置】</h4>
            <p>基于周期的配置框架与战术偏离建议（80字）。</p>
        </div>
        """
        
        payload = {
            "model": self.model_strategic, # R1
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 3000,
            "temperature": 0.4
        }
        try:
            resp = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=120)
            data = resp.json()
            if isinstance(data, str): data = json.loads(data)
            content = data['choices'][0]['message']['content']
            clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            return self._clean_html(clean_content)
        except:
            return "<p>首席策略师正在闭关推演...</p>"
            
    def _clean_html(self, text):
        text = text.replace("```html", "").replace("```", "").strip()
        return text
