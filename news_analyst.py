import requests
import xml.etree.ElementTree as ET
import os
import json
import time
from openai import OpenAI
from utils import retry, logger

class NewsAnalyst:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1") 
        self.model_name = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3") 

        if not self.api_key:
            logger.warning("⚠️ 未检测到 LLM_API_KEY")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    @retry(retries=3)
    def fetch_news_titles(self, keyword):
        """抓取新闻"""
        # ... (关键词逻辑保持不变) ...
        # 为节省篇幅，此处省略关键词映射代码，请保留原有的逻辑
        if "红利" in keyword: search_q = "中证红利 股息率"
        elif "白酒" in keyword: search_q = "白酒 茅台 批发价"
        elif "纳斯达克" in keyword: search_q = "美联储 纳斯达克 降息"
        elif "黄金" in keyword: search_q = "黄金 避险 美元指数"
        elif "医疗" in keyword: search_q = "医药 集采 创新药"
        else: search_q = keyword + " 行业分析"

        url = f"https://news.google.com/rss/search?q={search_q} when:2d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            titles = [item.find('title').text for item in root.findall('.//item')[:10]]
            return titles
        except:
            return []

    def analyze_fund_v4(self, fund_name, tech_data, market_ctx, news_titles):
        """
        V5.1 严厉逻辑校验版
        """
        if not self.client or not tech_data:
            return {"thesis": "数据不足", "action_advice": "观望", "confidence": 0, "pros":"", "cons":"", "glossary": {}}

        news_text = "; ".join(news_titles) if news_titles else "无重大新闻"
        
        # --- 🚀 核心升级：Prompt 增加硬性约束 ---
        prompt = f"""
        # Role
        你是一位**逻辑严密、极度厌恶风险**的量化基金经理。你的任务是基于数据做出**冷酷的判断**，严禁使用模棱两可的废话。

        # Data Input
        标的: {fund_name}
        1. **技术面**:
           - 周线趋势(长期): {tech_data['trend_weekly']} (注意: 周线DOWN = 熊市/调整期，此时日线反弹多为陷阱)
           - 日线趋势(短期): {tech_data['trend_daily']}
           - RSI: {tech_data['rsi']} (注意: 仅当 RSI<25 时才叫'极度超卖/钝化'；30-40是弱势区，不是底部)
           - 乖离率: {tech_data['bias_20']}%
        
        2. **环境**:
           - 市场风向: {market_ctx.get('north_label','未知')} (数值: {market_ctx.get('north_money','0')})
           - 舆情: {news_text}

        # Logic Rules (必须遵守的铁律)
        1. **趋势铁律**: 如果周线是 DOWN，禁止给出“强力买入”建议，最高信心分不得超过 6 分（除非 RSI < 20 抢反弹）。
        2. **RSI铁律**: 禁止随意使用“低位钝化”一词，除非 RSI < 25 且持续下跌。RSI 在 30-50 之间叫“弱势震荡”，不叫底。
        3. **一致性**: 如果建议“观望”，信心分必须低于 4 分；如果建议“买入”，必须说明具体的止损价位（如：跌破5日线）。

        # Output Requirements (Strict JSON)
        1. **thesis (核心逻辑)**: 100字。先定性（下跌中继/底部磨底/主升浪），再给理由。**必须解释为什么周线DOWN还要买（如果是的话）**。
        2. **action_advice**: [强力买入, 买入, 观望, 卖出, 坚决清仓]。
        3. **confidence**: 0-10 分。**严打通货膨胀**，普通行情只给 3-5 分。
        4. **pros/cons**: 各 2 点，必须具体（如：RSI底背离，而不是RSI低）。
        5. **glossary**: 解释 1 个文中用到的术语。

        # Example
        {{
            "thesis": "当前周线趋势向下(DOWN)，确认为中期空头排列。日线RSI(36)处于弱势区而非超卖区，所谓'反弹'缺乏动能。市场整体情绪低迷，不存在反转基础。当前任何上涨皆视为下跌中继，建议管住手，切勿在半山腰接飞刀。",
            "action_advice": "观望",
            "confidence": 2,
            "pros": "日线乖离率-5%有修复需求",
            "cons": "周线空头压制; 缺乏增量资金",
            "glossary": {{"下跌中继": "股价下跌途中暂时的休息，休息完后大概率继续跌。"}}
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a strict quantitative trader. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1 # 极低温度，确保逻辑严谨，不瞎编
            )
            
            content = response.choices[0].message.content
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {"thesis": "AI 思考超时", "action_advice": "观望", "confidence": 0, "pros": "", "glossary": {}}
