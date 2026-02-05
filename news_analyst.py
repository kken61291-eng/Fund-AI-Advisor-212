import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from openai import OpenAI
from utils import retry, logger

class NewsAnalyst:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1") 
        self.model_name = os.getenv("LLM_MODEL", "Pro/moonshotai/Kimi-K2.5") 
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url) if self.api_key else None

        # --- 板块逻辑矩阵 (V12.2) ---
        self.SECTOR_LOGIC_MAP = {
            "红利": "【债性思维】核心看点是'10年期国债收益率'和'股息率差'。利率上行利空红利。拥挤交易导致股息率下降是风险。",
            "煤炭": "【商品思维】核心看点是'期货价格'、'库存'和'旺季预期'。期现背离(期货跌股价涨)是诱多。旺季是强支撑。",
            "黄金": "【宏观思维】核心看点是'美债实际利率'(负相关)和'地缘政治'。避险情绪主导时忽略美元。流动性危机时黄金会被抛售。",
            "半导体": "【成长思维】核心看点是'费城半导体指数'、'国产替代'和'资本开支'。利率敏感。纳指大跌A股难独善其身。",
            "AI通信": "【映射思维】核心看点是'美股英伟达'表现。影子股逻辑。美股龙头破位A股必跌。警惕业绩无法落地的伪逻辑。",
            "证券": "【牛市旗手】核心看点是'两市成交额'和'政策'。成交额萎缩(<8000亿)时的上涨为诱多。放量突破才是真启动。",
            "沪深300": "【国运思维】核心看点是'汇率'(外资)和'社融'。汇率贬值且北向流出，反弹多为一日游。",
            "新能源": "【产能思维】核心看点是'产能出清'和'价格战'。去库周期中，任何上涨先视为超跌反弹。",
            "医药": "【政策思维】核心看点是'集采'和'反腐'。创新药看美债利率。受政策扰动大。",
            "日经": "【汇率思维】核心看点是'日元汇率'。日元贬值利好日股。警惕央行加息。",
            "纳指": "【流动性思维】核心看点是'降息预期'和'巨头财报'。美债利率飙升是杀估值利空。"
        }

    def _get_time_label(self, pub_date_str):
        """
        [V12.4 新增] 计算新闻的新旧程度
        """
        try:
            if not pub_date_str: return ""
            pub_dt = parsedate_to_datetime(pub_date_str)
            if pub_dt.tzinfo: pub_dt = pub_dt.replace(tzinfo=None)
            
            delta = datetime.now() - pub_dt
            days = delta.days
            
            if days < 1: return " [新!]"
            elif days < 3: return f" [{days}天前]"
            elif days < 30: return f" [{days}天前]"
            else: return " [旧闻]" # 超过一个月
        except: return ""

    @retry(retries=2)
    def fetch_news_titles(self, keyword):
        # 关键词构建
        search_q = keyword + " 行业分析"
        if "红利" in keyword: search_q = "A股 红利指数 股息率"
        elif "美股" in keyword: search_q = "美联储 降息 纳斯达克 宏观"
        elif "半导体" in keyword: search_q = "半导体 周期 涨价"
        elif "黄金" in keyword: search_q = "黄金 避险 美元指数"
        elif "证券" in keyword: search_q = "A股 成交额 券商"
        
        # 移除 when:2d 以获取更多上下文，但必须配合时间标签使用
        url = f"https://news.google.com/rss/search?q={search_q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        
        titles = []
        try:
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            
            for item in root.findall('.//item')[:5]:
                raw_title = item.find('title').text
                pub_date = item.find('pubDate').text
                
                # --- [V12.4] 注入时间标签 ---
                time_label = self._get_time_label(pub_date)
                
                # 如果是"旧闻"，AI 看到这个标签就会降低权重
                full_title = f"{raw_title}{time_label}"
                titles.append(full_title)
                
            return titles
        except: return []

    def _get_logic_chain(self, fund_name):
        for key, logic in self.SECTOR_LOGIC_MAP.items():
            if key in fund_name: return logic
        return "【通用思维】缩量上涨为诱多，放量滞涨为出货。关注量价配合。"

    def analyze_fund_v4(self, fund_name, tech, market_ctx, news):
        if not self.client: return {"comment": "AI Offline", "risk_alert": "", "adjustment": 0}

        risk = tech.get('risk_factors', {'bollinger_pct_b': 0.5, 'vol_ratio': 1.0, 'divergence': '无'})
        sector_logic = self._get_logic_chain(fund_name)

        tech_context = f"""
        - 基准分: {tech['quant_score']}
        - 趋势: 周线{tech['trend_weekly']}, MACD{tech['macd']['trend']}
        - 资金: OBV斜率 {tech['flow']['obv_slope']}
        - 量比: {risk['vol_ratio']} (0.8以下缩量)
        - 背离: {risk['divergence']} (顶背离需警惕)
        """

        prompt = f"""
        # Role: 资深行业分析师 (Sector Specialist)
        # Task: 基于【专属逻辑链】和【新闻时效性】进行测谎。
        
        # Context
        - 标的: {fund_name}
        - 宏观: {str(market_ctx)}
        - 舆情: {str(news)} (注意标题后的 [新!] 或 [旧闻] 标签)
        - 技术: {tech_context}

        # 🧬 专属逻辑链
        >>> {sector_logic} <<<

        # 判决法则
        1. **时效过滤**: 如果舆情都是"[旧闻]"或"[30天前]"，忽略其影响，以技术面为主。
        2. **逻辑验证**: 新闻/盘面是否符合逻辑链？(如: 券商涨但没放量 -> 假突破)。
        3. **量价铁律**: 缩量(量比<0.8)上涨 + OBV流出 = **诱多，必须重罚**。

        # Output JSON
        {{
            "comment": "80字深度分析。引用逻辑链关键词。指出新闻是否过期。",
            "risk_alert": "20字致命风险点。",
            "adjustment": (整数 -100 到 +50) 
        }}
        """

        try:
            res = self.client.chat.completions.create(model=self.model_name, messages=[{"role":"user","content":prompt}], response_format={"type":"json_object"}, temperature=0.4)
            data = json.loads(res.choices[0].message.content)
            if 'adjustment' not in data: data['adjustment'] = 0
            return data
        except Exception as e:
            logger.error(f"AI 分析错误: {e}")
            return {"comment": "AI服务异常", "risk_alert": "无", "adjustment": 0}

    def review_report(self, summary):
        if not self.client: return "<p>CIO Offline</p>"
        prompt = f"""
        # Role: CIO
        # Strategy: Core + Satellite
        # Plan: {summary}
        # Task: 宏观一致性 + 仓位评估 + 最终裁决
        # Output HTML: <div class='cio-seal'>CIO APPROVED</div><h3>CIO 战略审计</h3><p><strong>宏观定调：</strong>...</p><p><strong>双轨评估：</strong>...</p><p class='warning'><strong>最终裁决：</strong>...</p>
        """
        try:
            res = self.client.chat.completions.create(model=self.model_name, messages=[{"role":"user","content":prompt}], temperature=0.6)
            return res.choices[0].message.content.strip().replace('```html', '').replace('```', '')
        except: return "CIO Audit Failed."

    def advisor_review(self, summary, market_ctx):
        if not self.client: return ""
        prompt = f"""
        # Role: 玄铁先生 (资产配置专家)
        # Context: {market_ctx} | Plan: {summary}
        # Task: 为场外基民提供独立验证。
        # Output HTML: <div class='advisor-title'>🗡️ 玄铁先生·场外实战复盘</div><p><strong>【势·验证】：</strong>...</p><p><strong>【术·底仓】：</strong>...</p><p><strong>【断·进攻】：</strong>...</p>
        """
        try:
            res = self.client.chat.completions.create(model=self.model_name, messages=[{"role":"user","content":prompt}], temperature=0.5)
            return res.choices[0].message.content.strip().replace('```html', '').replace('```', '')
        except: return "Advisor Offline."
