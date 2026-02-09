import yaml
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
# from market_scanner import MarketScanner # [移除] 不需要了
from technical_analyzer import TechnicalAnalyzer
from valuation_engine import ValuationEngine
from portfolio_tracker import PortfolioTracker
from utils import send_email, logger, LOG_FILENAME

# --- 全局配置 ---
DEBUG_MODE = True  
tracker_lock = threading.Lock()

def load_config():
    # ... (保持不变) ...
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return {"funds": [], "global": {"base_invest_amount": 1000, "max_daily_invest": 5000}}

# ... (calculate_position_v13 保持不变) ...
def calculate_position_v13(tech, ai_adj, val_mult, val_desc, base_amt, max_daily, pos, strategy_type, fund_name):
    # 略... 请保持原代码
    base_score = tech.get('quant_score', 50)
    # ...
    # 必须保留这个函数的完整逻辑
    # ...
    if tech.get('tech_cro_signal') == "VETO":
        return 0, "观望", False, 0
    
    # 简单模拟返回，请使用您原来的完整逻辑
    return 0, "观望", False, 0 

# ... (render_html_report_v13 保持不变) ...
def render_html_report_v13(all_news, results, cio_html, advisor_html):
    # 略... 请保持原代码
    return "<html>...</html>"

def process_single_fund(fund, config, fetcher, tracker, val_engine, analyst, market_context, base_amt, max_daily):
    # [修改] 参数移除了 scanner，增加了 market_context
    res = None
    cio_log = ""
    used_news = []
    
    try:
        logger.info(f"Analyzing {fund['name']}...")
        
        # 1. 读本地数据
        data = fetcher.get_fund_history(fund['code'])
        if data is None or data.empty: 
            return None, "", []

        # 2. 技术指标
        tech = TechnicalAnalyzer.calculate_indicators(data)
        if not tech: return None, "", []
        
        # 3. 估值
        try:
            val_mult, val_desc = val_engine.get_valuation_status(fund.get('index_name'), fund.get('strategy_type'))
        except:
            val_mult, val_desc = 1.0, "估值异常"

        with tracker_lock: pos = tracker.get_position(fund['code'])

        # 4. AI 分析
        ai_adj = 0; ai_res = {}
        should_run_ai = True # 默认开启，因为现在是本地快速运行

        if analyst and should_run_ai:
            cro_signal = tech.get('tech_cro_signal', 'PASS')
            fuse_level = 3 if cro_signal == 'VETO' else (1 if cro_signal == 'WARN' else 0)
            
            risk_payload = {
                "fuse_level": fuse_level,
                "risk_msg": tech.get('tech_cro_comment', '常规监控')
            }
            
            try:
                # [关键] 传入全量 market_context 作为 news 参数
                # V3 模型会阅读这 1.5万字 的新闻，结合技术指标给出判断
                ai_res = analyst.analyze_fund_v5(fund['name'], tech, None, market_context, risk_payload)
                ai_adj = ai_res.get('adjustment', 0)
            except Exception as e:
                logger.error(f"AI Analysis Failed: {e}")
                ai_res = {"bull_view": "Error", "bear_view": "Error", "comment": "Offline", "adjustment": 0}

        # 5. 算分与决策
        # 注意：这里需要确保 calculate_position_v13 已经定义
        # 为了演示完整性，请确保前面有这个函数
        # 这里用伪代码表示调用
        # amt, lbl, is_sell, s_val = calculate_position_v13(...)
        # 实际代码请保留您原来的
        amt = 0; lbl = "观望"; is_sell = False; s_val = 0
        
        # 6. 记账
        # ...

        # 7. 组装结果
        bull = ai_res.get('bull_view') or ai_res.get('bull_say', '无')
        bear = ai_res.get('bear_view') or ai_res.get('bear_say', '无')
        if bull != '无':
            logger.info(f"🗣️ [投委会 {fund['name']}] CGO:{bull[:20]}... | CRO:{bear[:20]}...")

        res = {
            "name": fund['name'], "code": fund['code'], 
            "amount": amt, "sell_value": s_val, "position_type": lbl, "is_sell": is_sell, 
            "tech": tech, "ai_analysis": ai_res, "history": [], # tracker.get_history...
            "pos_cost": pos.get('cost', 0), "pos_shares": pos.get('shares', 0)
        }
    except Exception as e:
        logger.error(f"Process Error {fund['name']}: {e}")
        return None, "", []
    return res, cio_log, used_news

def main():
    config = load_config()
    fetcher = DataFetcher()
    # scanner = MarketScanner() # 移除
    tracker = PortfolioTracker()
    val_engine = ValuationEngine()
    
    logger.info(f">>> [V15.14] Startup | LOCAL_MODE=True | News Source: Local Cache + Live Patch")
    tracker.confirm_trades()
    try: analyst = NewsAnalyst()
    except: analyst = None

    # [核心修改] 获取全量舆情上下文
    logger.info("📖 正在构建全天候舆情上下文 (Local + Live)...")
    market_context = analyst.get_market_context() if analyst else "无新闻数据"
    logger.info(f"🌍 舆情上下文长度: {len(market_context)} 字符")
    
    # 这里的 news_list 仅用于 UI 展示，可以简单解析 market_context 或者置空
    # 为了 UI 兼容，我们简单构造一个列表
    all_news_seen = [{"title": line, "time": ""} for line in market_context.split('\n')[:10]]

    results = []; cio_lines = [f"【宏观环境】: (见独立审计报告)\n"]
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_fund = {executor.submit(
            process_single_fund, 
            fund, config, fetcher, tracker, val_engine, analyst, market_context, 
            config['global']['base_invest_amount'], config['global']['max_daily_invest']
        ): fund for fund in config.get('funds', [])}
        
        for future in as_completed(future_to_fund):
            try:
                res, log, _ = future.result()
                if res: 
                    results.append(res)
                    cio_lines.append(log)
            except Exception as e: logger.error(f"Thread Error: {e}")

    if results:
        results.sort(key=lambda x: -x['tech'].get('final_score', 0))
        full_report = "\n".join(cio_lines)
        
        cio_html = analyst.review_report(full_report, market_context) if analyst else "<p>CIO Missing</p>"
        advisor_html = analyst.advisor_review(full_report, market_context) if analyst else "<p>Advisor Offline</p>"
        
        # 假设 render_html_report_v13 存在
        from main import render_html_report_v13 as original_render
        html = original_render(all_news_seen, results, cio_html, advisor_html) 
        
        send_email("🗡️ 玄铁量化 V15.14 铁拳决议 (Full Context)", html, attachment_path=LOG_FILENAME)

if __name__ == "__main__": main()
