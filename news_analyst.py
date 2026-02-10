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
        # 战术执行 (快思考): V3.2 - 负责 CGO/CRO/CIO 实时信号
        self.model_tactical = "Pro/deepseek-ai/DeepSeek-V3.2"      
        # 战略推理 (慢思考): R1 - 负责 宏观策略/复盘审计
        self.model_strategic = "Pro/deepseek-ai/DeepSeek-R1"  

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # [RAG] 加载板块实战经验库
        self.knowledge_base = self._load_knowledge_base()

    def _load_knowledge_base(self):
        """加载 JSON 经验库，若不存在则返回空"""
        try:
            if os.path.exists('knowledge_base.json'):
                with open('knowledge_base.json', 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.warning(f"⚠️ 无法加载经验库: {e}")
            return {}

    def _fetch_live_patch(self):
        """
        [7x24全球财经电报]
        UI还原关键：只返回 [时间] 标题 格式，不拼摘要，配合 main.py 还原 V15.14 样式
        """
        try:
            time.sleep(1)
            # 使用电报接口
            df = ak.stock_telegraph_em()
            news = []
            
            # 保持 50 条的大容量，但格式回归经典
            for i in range(min(50, len(df))):
                title = str(df.iloc[i].get('title') or '')
                t = str(df.iloc[i].get('public_time') or '')
                if len(t) > 10: t = t[5:16] 
                
                # 宽松过滤
                if self._is_valid_news(title):
                    # [回归 V15.14] 纯净格式，不带 content
                    item_str = f"[{t}] {title}"
                    news.append(item_str)
            return news
        except Exception as e:
            logger.warning(f"Live news fetch error: {e}")
            return []

    def _is_valid_news(self, title):
        """
        [宽松过滤器]
        保留绝大多数新闻，只过滤明显的空数据或极短数据
        """
        if not title: 
            return False
        
        # 只过滤极短的无效标题
        if len(title) < 2: 
            return False
            
        return True

    def get_market_context(self, max_length=30000):
        news_lines = []
        today_str = get_beijing_time().strftime("%Y-%m-%d")
        file_path = f"data_news/news_{today_str}.jsonl"
        
        # 1. 优先读取实时电报
        live_news = self._fetch_live_patch()
        if live_news:
            news_lines.extend(live_news)
            
        # 2. 补充本地缓存的历史新闻
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            item = json.loads(line)
                            title = str(item.get('title', ''))
                            if not self._is_valid_news(title): continue
                                
                            t_str = str(item.get('time', ''))
                            if len(t_str) > 10: t_str = t_str[5:16]
                            
                            # [回归 V15.14] 纯净格式
                            news_entry = f"[{t_str}] {title}"
                            news_lines.append(news_entry)
                        except: pass
            except Exception as e:
                logger.error(f"读取新闻缓存失败: {e}")
        
        # 去重
        unique_news = []
        seen = set()
        for n in news_lines:
            # 简单文本去重
            if n not in seen:
                seen.add(n)
                unique_news.append(n)
        
        # 喂给 AI 的全量文本
        # 使用 \n 连接，main.py 会 split('\n')
        final_text = "\n".join(unique_news[:80]) 
        
        if len(final_text) > max_length:
            return final_text[:max_length] + "\n...(早期消息已截断)"
        
        return final_text if final_text else "今日暂无重大新闻。"

    def _clean_json(self, text):
        try:
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```', '', text)
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]
            text = re.sub(r',\s*}', '}', text)
            text = re.sub(r',\s*]', ']', text)
            return text
        except: return "{}"
    
    def _clean_html(self, text):
        text = text.replace("```html", "").replace("```", "").strip()
        return text

    @retry(retries=1, delay=2)
    def analyze_fund_v5(self, fund_name, tech, macro, news, risk, strategy_type="core"):
        """
        [战术层] 联邦投委会辩论系统 (V3.2) - RAG 增强版
        """
        kb_data = self.knowledge_base.get(strategy_type, {})
        expert_rules = "\n".join([f"- {r}" for r in kb_data.get('rules', [])])
        if not expert_rules: expert_rules = "- 无特殊经验，按常规逻辑分析。"

        fuse_level = risk['fuse_level']
        fuse_msg = risk['risk_msg']
        trend_score = tech.get('quant_score', 50)
        
        prompt = f"""
        【系统架构】鹊知风投委会 | RAG增强模式
        
        【标的信息】
        标的: {fund_name} (策略类型: {strategy_type})
        趋势强度: {trend_score}/100 | 熔断状态: Level{fuse_level} | 硬约束: {fuse_msg}
        技术指标: RSI={tech.get('rsi',50)} | MACD={tech.get('macd',{}).get('trend','-')}
        
        【💀 鹊知风实战经验库】
        {expert_rules}
        
        【舆情扫描】
        {str(news)[:20000]}

        【任务】
        输出严格JSON，不要Markdown。Adjustment为整数。

        【输出格式】
        {{
            "bull_view": "...",
            "bear_view": "...",
            "chairman_conclusion": "...",
            "decision": "EXECUTE|REJECT|HOLD",
            "adjustment": 0
        }}
        """
        
        payload = {
            "model": self.model_tactical,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 800,
            "response_format": {"type": "json_object"}
        }
        
        try:
            resp = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=payload, timeout=90)
            if resp.status_code != 200:
                return self._get_fallback_result()
            
            content = resp.json()['choices'][0]['message']['content']
            result = json.loads(self._clean_json(content))
            
            try: result['adjustment'] = int(result.get('adjustment', 0))
            except: result['adjustment'] = 0

            if fuse_level >= 2:
                result['decision'] = 'REJECT'
                result['adjustment'] = -30
                result['chairman_conclusion'] = f'[熔断] {fuse_msg}'

            return result
        except Exception as e:
            logger.error(f"AI Analysis Failed {fund_name}: {e}")
            return self._get_fallback_result()

    def _get_fallback_result(self):
        return {"bull_view": "Error", "bear_view": "Error", "chairman_conclusion": "Offline", "decision": "HOLD", "adjustment": 0}

    @retry(retries=2, delay=5)
    def review_report(self, report_text, macro_str):
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
        【系统角色】鹊知风CIO | 机构级复盘备忘录 | 日期: {current_date}
        【输入数据】宏观: {macro_str[:2500]} | 交易: {report_text[:3000]}
        【任务】1.精确归因 2.策略适配评估
        【输出】HTML格式CIO备忘录。
        """
        return self._call_r1(prompt)

    @retry(retries=2, delay=5)
    def advisor_review(self, report_text, macro_str):
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
        【系统角色】鹊知风Red Team | 独立审计顾问 | 日期: {current_date}
        【输入数据】宏观: {macro_str[:2500]} | 交易: {report_text[:3000]}
        【任务】五问压力测试
        【输出】HTML格式审计报告。
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
