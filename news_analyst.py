import requests
import json
import os
import re
import akshare as ak
import time
import random
from datetime import datetime
from utils import logger, retry, get_beijing_time

class NewsAnalyst:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.model_tactical = "Pro/deepseek-ai/DeepSeek-V3.2"      
        self.model_strategic = "Pro/deepseek-ai/DeepSeek-R1"  

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _fetch_live_patch(self):
        try:
            time.sleep(1)
            df = ak.stock_news_em(symbol="要闻")
            news = []
            for i in range(min(5, len(df))):
                title = str(df.iloc[i].get('新闻标题') or df.iloc[i].get('title'))
                t = str(df.iloc[i].get('发布时间') or df.iloc[i].get('public_time'))
                if len(t) > 10: t = t[5:16] 
                news.append(f"[{t}] {title} (Live)")
            return news
        except:
            return []

    def get_market_context(self, max_length=20000):
        news_lines = []
        today_str = get_beijing_time().strftime("%Y-%m-%d")
        file_path = f"data_news/news_{today_str}.jsonl"
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            item = json.loads(line)
                            t_str = str(item.get('time', ''))
                            if len(t_str) > 10: t_str = t_str[5:16]
                            news_lines.append(f"[{t_str}] {item.get('title')}")
                        except: pass
            except Exception as e:
                logger.error(f"读取新闻缓存失败: {e}")
        
        live_news = self._fetch_live_patch()
        if live_news:
            news_lines.extend(live_news)
            
        unique_news = []
        seen = set()
        for n in reversed(news_lines):
            if n not in seen:
                seen.add(n)
                unique_news.append(n)
        
        final_text = "\n".join(unique_news)
        
        if len(final_text) > max_length:
            return final_text[:max_length] + "\n...(早期消息已截断)"
        
        return final_text if final_text else "今日暂无重大新闻。"

    def _clean_json(self, text):
        try:
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            code_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
            if code_match: return code_match.group(1)
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1: return text[start:end+1]
            return "{}"
        except: return "{}"
    
    def _clean_html(self, text):
        text = text.replace("```html", "").replace("```", "").strip()
        return text

    @retry(retries=1, delay=2)
    def analyze_fund_v5(self, fund_name, tech, macro, news, risk):
        fuse_level = risk['fuse_level']
        fuse_msg = risk['risk_msg']
        trend_score = tech.get('quant_score', 50)
        rsi = tech.get('rsi', 50)
        macd = tech.get('macd', {})
        vol_ratio = tech.get('risk_factors', {}).get('vol_ratio', 1.0)
        
        prompt = f"""
        【系统任务】
        你现在是玄铁量化基金的投研系统。请模拟 CGO(动量)、CRO(风控)、CIO(总监) 三位专家的辩论过程，并输出最终决策 JSON。
        
        【输入数据】
        标的: {fund_name}
        技术因子:
        - 趋势强度: {trend_score} (0-100)
        - RSI(14): {rsi}
        - MACD: {macd.get('trend', '未知')}
        - 成交量偏离(VR): {vol_ratio}
        
        风险因子:
        - 熔断等级: {fuse_level} (0-3，>=2为限制交易)
        - 风控指令: {fuse_msg}
        
        舆情因子:
        {str(news)[:15000]}

        --- 角色定义 (请丰富人设细节) ---
        1. **CGO (动量猎手)**: 
           - 风格: 激进、敏锐。专注于右侧突破。
           - 任务: 结合MACD金叉、RSI区间和新闻利好，寻找做多理由。
           - 纪律: 若趋势<50，必须承认"当前无势可借"。

        2. **CRO (合规铁闸)**: 
           - 风格: 冷酷、保守。专注于左侧避险。
           - 任务: 泼冷水。指出VR背离、熔断限制或新闻利空。
           - 纪律: 必须引用具体数据（如"VR仅0.6"）来驳斥CGO。

        3. **CIO (最终裁决)**: 
           - 风格: 平衡、果断。
           - 任务: 权衡胜率与赔率。给出明确的"买入/卖出/观望"指令。

        【输出格式-严格JSON】
        请输出 JSON，不要 Markdown。
        {{
            "bull_view": "CGO观点 (80字以内): 引用具体技术指标和新闻，阐述进攻逻辑。",
            "bear_view": "CRO观点 (80字以内): 引用风控数据，阐述防守逻辑。",
            "chairman_conclusion": "CIO裁决 (100字以内): 综合多空双方，给出最终操作指令及仓位建议。",
            "adjustment": 整数数值 (-30 到 +30)
        }}
        """
        
        payload = {
            "model": self.model_tactical,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3, # 稍微提高温度，增加丰富性
            "max_tokens": 1500,
            "response_format": {"type": "json_object"}
        }
        
        try:
            resp = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=90)
            if resp.status_code != 200:
                return {"bull_view": "API Error", "bear_view": "API Error", "comment": "API Error", "adjustment": 0}
            
            content = resp.json()['choices'][0]['message']['content']
            result = json.loads(self._clean_json(content))
            
            if "chairman_conclusion" in result and "comment" not in result:
                result["comment"] = result["chairman_conclusion"]
            return result
        except Exception as e:
            logger.error(f"AI Analysis Failed {fund_name}: {e}")
            return {"bull_view": "解析失败", "bear_view": "解析失败", "comment": "JSON Error", "adjustment": 0}

    @retry(retries=2, delay=5)
    def review_report(self, report_text, macro_str):
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
        【系统角色】CIO (首席投资官) | 日期: {current_date}
        【输入数据】
        1. 全天候宏观舆情: {macro_str[:2000]}
        2. 交易报告: {report_text}
        
        【任务】使用 DeepSeek-R1 思维链进行宏观定调、归因分析和战略指令下达。请模仿高盛内部备忘录风格，专业、冷峻。
        """
        return self._call_r1(prompt)

    @retry(retries=2, delay=5)
    def advisor_review(self, report_text, macro_str):
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
        【系统角色】独立审计顾问 (Red Team) | 日期: {current_date}
        【输入数据】
        1. 全天候宏观舆情: {macro_str[:2000]}
        2. CIO交易: {report_text}
        
        【任务】
        1. 盲点警示：指出CIO可能忽略的宏观风险。
        2. 逻辑压力测试：质疑今日交易的合理性。
        3. 最终验证：给出"通过"或"驳回"建议。
        """
        return self._call_r1(prompt)

    def _call_r1(self, prompt):
        payload = {
            "model": self.model_strategic, 
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,
            "temperature": 0.3 
        }
        try:
            resp = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=180)
            content = resp.json()['choices'][0]['message']['content']
            return self._clean_html(content)
        except:
            return "<p>分析生成中...</p>"
