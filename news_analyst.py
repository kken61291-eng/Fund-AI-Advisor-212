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
        
        # 修正：优先读取环境变量，如果没有设置，才默认回退到 DeepSeek
        # 这样您在 YAML 里改了 LLM_MODEL，这里就会自动生效
        self.model_name = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3") 
        
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.client = None
            logger.warning("未配置 LLM_API_KEY，AI 分析功能将不可用")

    @retry(retries=3)
    def fetch_news_titles(self, keyword):
        """抓取谷歌新闻RSS (全量版逻辑)"""
        # 针对不同板块优化搜索词，获取更精准的行业催化剂
        if "红利" in keyword: search_q = "A股 红利指数 股息率"
        elif "白酒" in keyword: search_q = "白酒 茅台 批发价 库存"
        elif "美股" in keyword: search_q = "美联储 降息 纳斯达克"
        elif "港股" in keyword: search_q = "恒生科技 外资流向"
        elif "医疗" in keyword: search_q = "医药集采 创新药 出海"
        elif "黄金" in keyword: search_q = "黄金价格 避险 美元"
        elif "半导体" in keyword: search_q = "半导体 周期 国产替代"
        elif "光伏" in keyword: search_q = "光伏 产能 过剩 价格"
        elif "银行" in keyword: search_q = "银行 息差 坏账"
        else: search_q = keyword + " 行业分析"

        url = f"https://news.google.com/rss/search?q={search_q} when:2d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            # 获取前 5 条新闻作为上下文
            titles = [item.find('title').text for item in root.findall('.//item')[:5]]
            return titles
        except:
            return []

    def analyze_fund_v4(self, fund_name, tech_data, market_ctx, news_titles):
        """
        V9.1 深度分析引擎 (适配 Kimi-K2.5 / DeepSeek)
        """
        if not self.client:
            return {"comment": "AI 未配置", "risk_alert": ""}

        # 整理输入数据
        score = tech_data['quant_score']
        rsi = tech_data['rsi']
        bias = tech_data['bias_20']
        trend_w = tech_data['trend_weekly']
        news_str = " | ".join(news_titles) if news_titles else "行业面平静"
        
        # 宏观环境
        macro_sentiment = market_ctx.get('north_label', '震荡')
        macro_val = market_ctx.get('north_money', '0%')

        # --- Prompt: 针对 Kimi 优化的长逻辑推理 ---
        prompt = f"""
        # Role
        你是一位拥有20年经验的**首席宏观对冲策略师**。你的特点是：**拒绝废话，只谈逻辑，洞察主力意图**。

        # Market Context
        - 标的名称: {fund_name}
        - 宏观环境: {macro_sentiment} ({macro_val})
        - 行业舆情: {news_str}

        # Quantitative Signals
        - 综合评分: {score}分 (0-100，>70为机会，<30为风险)
        - 长期趋势(周线): {trend_w}
        - 短期动能(RSI): {rsi} (30超卖，70超买)
        - 乖离率(Bias): {bias}%

        # Task
        请根据上述数据，输出一份**高含金量**的微型研报（JSON格式）。

        # Requirements
        1. **comment (核心逻辑)**: 
           - 限 60 字以内。
           - **必须包含**：技术面与基本面的共振点（或背离点）。
           - **关键信息**：主力是在洗盘还是出货？当前是左侧博弈还是右侧跟随？
           - 风格犀利：不要说"建议关注"，要说"倒车接人机会"或"诱多出货风险"。
        
        2. **risk_alert (关键风控)**:
           - 限 15 字以内。
           - 指出最致命的一个风险点（如：汇率波动、集采预期、技术破位）。

        # JSON Output Example
        {{
            "comment": "周线多头排列下，RSI回落至45属于良性洗盘。叠加美联储降息预期的行业利好，当前缩量回调是机构调仓迹象，建议右侧布局。",
            "risk_alert": "警惕上方60日线压制"
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a professional financial strategist. Output strictly valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3 # 保持理性
            )
            content = response.choices[0].message.content
            # 清洗可能的 markdown 符号
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
        except Exception as e:
            logger.error(f"AI 分析失败: {e}")
            return {"comment": "数据波动，建议结合技术指标观察。", "risk_alert": "市场不确定性"}
