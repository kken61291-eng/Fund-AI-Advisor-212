import requests
import json
import os
import re
import akshare as ak
import time
import random
import pandas as pd
from datetime import datetime
from utils import logger, retry, get_beijing_time

class NewsAnalyst:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        # 战术执行 (快思考): V3.2 - 负责 CGO/CRO/CIO 实时信号
        self.model_tactical = "Pro/deepseek-ai/DeepSeek-V3.2"      
        # 战略推理 (慢思考): R1 - 负责 宏观复盘/逻辑审计
        self.model_strategic = "Pro/deepseek-ai/DeepSeek-R1"  

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # [V15.16 改动] 移除 self.knowledge_base，不再加载任何预设规则

    def _clean_time(self, t_str):
        """统一时间格式为 MM-DD HH:MM"""
        try:
            if len(str(t_str)) >= 16:
                return str(t_str)[5:16]
            return str(t_str)
        except: return ""

    def _fetch_live_patch(self):
        """
        [7x24全球财经电报] - 双源抓取 (EastMoney + CLS)
        """
        news_list = []
        
        # 1. 东方财富
        try:
            df_em = ak.stock_telegraph_em()
            if df_em is not None and not df_em.empty:
                for i in range(min(50, len(df_em))):
                    title = str(df_em.iloc[i].get('title') or '')
                    content = str(df_em.iloc[i].get('content') or '')
                    t = self._clean_time(df_em.iloc[i].get('public_time'))
                    
                    if self._is_valid_news(title):
                        item_str = f"[{t}] [EM] {title}"
                        if len(content) > 10 and content != title:
                            item_str += f"\n   (摘要: {content[:300]})"
                        news_list.append(item_str)
        except Exception as e:
            logger.warning(f"Live EM fetch error: {e}")

        # 2. 财联社
        try:
            df_cls = ak.stock_telegraph_cls()
            if df_cls is not None and not df_cls.empty:
                for i in range(min(50, len(df_cls))):
                    title = str(df_cls.iloc[i].get('title') or '')
                    content = str(df_cls.iloc[i].get('content') or '')
                    raw_t = df_cls.iloc[i].get('ctime', df_cls.iloc[i].get('publish_time'))
                    
                    try:
                        if str(raw_t).isdigit():
                            dt = datetime.fromtimestamp(int(raw_t))
                            t = dt.strftime("%m-%d %H:%M")
                        else:
                            t = self._clean_time(raw_t)
                    except: t = ""

                    if not title and content: title = content[:30] + "..."

                    if self._is_valid_news(title):
                        item_str = f"[{t}] [CLS] {title}"
                        if len(content) > 10 and content != title:
                            item_str += f"\n   (摘要: {content[:300]})"
                        news_list.append(item_str)
        except Exception as e:
            logger.warning(f"Live CLS fetch error: {e}")

        return news_list

    def _is_valid_news(self, title):
        if not title: return False
        if len(title) < 2: return False
        return True

    def get_market_context(self, max_length=35000): 
        """
        [核心逻辑] 收集(Local+EM+CLS) -> 去重 -> 排序 -> 截断
        """
        news_candidates = []
        today_str = get_beijing_time().strftime("%Y-%m-%d")
        file_path = f"data_news/news_{today_str}.jsonl"
        
        # 1. 优先读取实时电报 (双源)
        live_news = self._fetch_live_patch()
        if live_news:
            news_candidates.extend(live_news)
            
        # 2. 补充本地缓存的历史新闻
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            item = json.loads(line)
                            title = str(item.get('title', ''))
                            if not self._is_valid_news(title): continue
                                
                            t_str = self._clean_time(item.get('time', ''))
                            source = item.get('source', 'Local')
                            src_tag = "[EM]" if source == "EastMoney" else ("[CLS]" if source == "CLS" else "[Local]")
                            
                            content = str(item.get('content') or item.get('digest') or "")
                            
                            news_entry = f"[{t_str}] {src_tag} {title}"
                            if len(content) > 10:
                                news_entry += f"\n   (摘要: {content[:300]})"
                                
                            news_candidates.append(news_entry)
                        except: pass
            except Exception as e:
                logger.error(f"读取新闻缓存失败: {e}")
        
        # 3. 去重 (基于标题)
        unique_news = []
        seen = set()
        for n in news_candidates:
            try:
                title_part = n.split('] ', 2)[-1].split('\n')[0]
            except:
                title_part = n.split('\n')[0]
                
            if title_part not in seen:
                seen.add(title_part)
                unique_news.append(n)
        
        # 4. 强制倒序
        try:
            unique_news.sort(key=lambda x: x[:17], reverse=True)
        except: pass 
        
        # 5. 截断
        final_list = []
        current_len = 0
        for news_item in unique_news:
            item_len = len(news_item)
            if current_len + item_len < max_length:
                final_list.append(news_item)
                current_len += item_len + 1 
            else:
                break
        
        final_text = "\n".join(final_list)
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
        [战术层] 联邦投委会 (V3.2) - 纯数据驱动 (无RAG干扰)
        """
        fuse_level = risk['fuse_level']
        fuse_msg = risk['risk_msg']
        trend_score = tech.get('quant_score', 50)
        
        # [V15.16] 提示词净化：移除所有关于“经验库”的描述，强制 AI 只看数据
        prompt = f"""
        【系统架构】鹊知风投委会 | 纯数据驱动模式 (Pure Data Driven)
        
        【标的信息】
        标的: {fund_name} (属性: {strategy_type})
        趋势强度: {trend_score}/100 | 熔断状态: Level{fuse_level} | 硬约束: {fuse_msg}
        技术指标: RSI={tech.get('rsi',50)} | MACD={tech.get('macd',{}).get('trend','-')}
        
        【实时舆情 (EastMoney + CLS双源)】
        {str(news)[:25000]}

        【任务】
        作为客观的量化交易员，请仅基于上述“技术指标”和“实时新闻”做出判断。
        禁止引用任何预设的、外部的或未知的经验规则。
        若新闻无相关内容，请完全依赖技术指标。

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
        """
        [战略层] CIO 复盘 (R1) - 纯逻辑归纳 (无RAG)
        """
        current_date = datetime.now().strftime("%Y年%m月%d日")
        
        # [V15.16] 提示词净化：移除RAG注入，改为纯粹的宏观与微观对照分析
        prompt = f"""
        【系统角色】鹊知风CIO | 首席投资官 | 日期: {current_date}
        
        【输入数据】
        1. 宏观环境 (基于新闻流): {macro_str[:2500]}
        2. 交易明细 (投委会决策): {report_text[:3000]}
        
        【任务】
        请基于上述信息，撰写一份《每日投资复盘备忘录》。
        1. 宏观定调：根据新闻判断今日市场情绪（恐慌/贪婪/分歧）。
        2. 策略一致性检查：投委会的买卖操作是否符合今日的宏观基调？
        3. 风险提示：指出数据中隐含的风险点。
        
        注意：不要臆造不存在的规则，只针对已发生的数据进行点评。
        
        【输出】HTML格式CIO备忘录。
        """
        return self._call_r1(prompt)

    @retry(retries=2, delay=5)
    def advisor_review(self, report_text, macro_str):
        """
        [审计层] Red Team 顾问 (R1) - 逻辑自洽性审计
        """
        current_date = datetime.now().strftime("%Y年%m月%d日")
        
        prompt = f"""
        【系统角色】鹊知风Red Team | 独立风控顾问 | 日期: {current_date}
        
        【输入数据】
        宏观: {macro_str[:2500]} | 交易: {report_text[:3000]}
        
        【任务】
        寻找“数据”与“决策”之间的逻辑漏洞。
        例如：如果宏观显示重大利空，但投委会却满仓买入，这就是逻辑漏洞。
        
        【五问压力测试】
        Q1: 决策是否过于激进?
        Q2: 是否忽视了宏观风险?
        Q3: 仓位控制是否合理?
        Q4: 交易方向是否与趋势背离?
        Q5: 是否存在情绪化交易?
        
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
