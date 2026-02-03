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
        # 建议使用 deepseek-ai/DeepSeek-V3 或 Qwen/Qwen2.5-72B-Instruct 以获得最佳逻辑能力
        self.model_name = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3") 

        if not self.api_key:
            logger.warning("⚠️ 未检测到 LLM_API_KEY，AI 分析功能将跳过")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    @retry(retries=3)
    def fetch_news_titles(self, keyword):
        """抓取新闻 (增加抓取数量以提供更多上下文)"""
        if "红利" in keyword: search_q = "中证红利 股息率"
        elif "白酒" in keyword: search_q = "白酒 茅台 批发价" # 更专业的关键词
        elif "纳斯达克" in keyword: search_q = "美联储 纳斯达克 降息"
        elif "黄金" in keyword: search_q = "黄金 避险 美元指数"
        elif "医疗" in keyword: search_q = "医药 集采 创新药"
        else: search_q = keyword + " 行业分析"

        url = f"https://news.google.com/rss/search?q={search_q} when:2d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            # 获取前 10 条，让 AI 有足够的信息筛选
            titles = [item.find('title').text for item in root.findall('.//item')[:10]]
            return titles
        except:
            return []

    def analyze_fund_v4(self, fund_name, tech_data, market_ctx, news_titles):
        """
        V4.5 机构级深度分析引擎
        """
        if not self.client:
            return {"thesis": "未配置API", "action_advice": "观望", "pros":"", "cons":""}

        if not tech_data:
            return {"thesis": "数据不足", "action_advice": "观望", "pros":"", "cons":""}

        news_text = "; ".join(news_titles) if news_titles else "近期行业无重大特异性新闻，关注宏观情绪。"
        
        # --- 🚀 核心升级：机构级 Prompt ---
        prompt = f"""
        # Role
        你是一席位管理百亿资金的**宏观对冲基金经理**（类似于 Ray Dalio 或 Howard Marks 的风格）。你极其厌恶风险，只在胜率超过 70% 时才会出手。你的决策风格是：**基于数据，逻辑严密，语言犀利，拒绝模棱两可**。

        # Task
        请根据以下多维数据，对标的【{fund_name}】进行深度投资价值分析。

        # Data Input
        1. **技术面结构 (Technical Structure)**:
           - 长期趋势(周线): {tech_data['trend_weekly']} (注意：周线决定方向，日线决定买点。周线向下时，日线的反弹往往是逃命波)
           - 短期状态(日线): {tech_data['trend_daily']}
           - 动能指标: RSI = {tech_data['rsi']} (RSI<30 超卖，RSI>70 超买。注意：单边下跌行情中，RSI 低位钝化是常态，非买入理由)
           - 均线乖离: 价格偏离MA20 {tech_data['bias_20']}% (负偏离度极大时才存在均值回归可能)
        
        2. **宏观与情绪 (Macro & Sentiment)**:
           - 北向/主力资金: {market_ctx.get('north_label','未知')} (资金流向代表聪明的钱)
           - 舆情面: {news_text}

        # Output Requirements (Strict JSON)
        请输出 JSON 格式，字段要求如下：
        
        1. **thesis (核心逻辑 - 重点)**: 
           - 长度要求 100-150 字。
           - 必须包含**“时空分析”**：结合周线的大方向和日线的位置。
           - 必须包含**“博弈分析”**：现在的价格是主力在诱多还是挖坑？
           - 给出明确的结论：是“下跌中继”、“底部磨底”还是“主升浪起点”？
        
        2. **pros (多头逻辑)**: 列出 2-3 点具体的利多因素（如：RSI底背离、行业利好落地）。
        3. **cons (空头逻辑)**: 列出 2-3 点具体的利空因素（如：周线空头排列、外资流出）。
        
        4. **action_advice (操作指令)**: 
           - 必须从以下选项中选择一个最精准的：
             [强力买入 (胜率>80%), 分批建仓 (胜率60%), 观望 (看不清/下跌中), 止盈减仓 (高位滞涨), 坚决清仓 (趋势破位)]
        
        5. **risk_warning (风控底线)**: 如果发生什么情况（如跌破某均线、突发利空），必须无条件离场？

        # Example Output Style
        {{
            "thesis": "当前标的处于典型的'周线空头、日线超跌'的左侧区间。虽然RSI(25)显示极度超卖，且偏离MA20达-8%，存在技术性反抽需求，但周线趋势(DOWN)表明中期调整未结束。考虑到北向资金持续流出，当前任何反弹皆视为减仓机会，而非反转。建议等待价格重新站上20日线，或出现明确的底部放量信号后再行右侧布局。",
            "action_advice": "观望",
            "pros": "日线严重超跌，乖离率有修复需求；部分行业利空已出尽",
            "cons": "周线下降通道完好，上方套牢盘沉重；宏观流动性紧缩",
            "risk_warning": "若放量跌破前低，则开启新一轮下跌，需无条件止损。"
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a senior fund manager. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3 # 降低随机性，增加专业度和严谨性
            )
            
            content = response.choices[0].message.content
            # 清洗 markdown
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {"thesis": "AI 深度思考超时", "action_advice": "观望", "pros": str(e)[:20], "cons":""}
