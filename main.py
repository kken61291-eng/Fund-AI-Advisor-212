import yaml
import os
import threading
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入核心模块
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
from technical_analyzer import TechnicalAnalyzer
from valuation_engine import ValuationEngine
from portfolio_tracker import PortfolioTracker
from utils import send_email, logger, LOG_FILENAME

# 导入 UI 渲染模块
from ui_renderer import render_html_report_v17

# --- 全局配置 ---
TEST_MODE = True   # 【🔥修改这里】True = 仅测试第一个标的; False = 运行全量
tracker_lock = threading.Lock()

def load_config():
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"配置文件读取失败: {e}")
        return {"funds": [], "global": {"base_invest_amount": 1000, "max_daily_invest": 5000}}

def calculate_position_v13(tech, ai_adj, ai_decision, val_mult, val_desc, base_amt, max_daily, pos, strategy_type, fund_name):
    """
    V13 核心资金管理策略
    """
    base_score = tech.get('quant_score', 50)
    try: ai_adj_int = int(ai_adj)
    except: ai_adj_int = 0

    tactical_score = max(0, min(100, base_score + ai_adj_int))
    
    if ai_decision == "REJECT": tactical_score = 0 
    elif ai_decision == "HOLD" and tactical_score >= 60: tactical_score = 59
            
    tech['final_score'] = tactical_score
    tech['ai_adjustment'] = ai_adj_int
    tech['valuation_desc'] = val_desc
    cro_signal = tech.get('tech_cro_signal', 'PASS')
    
    tactical_mult = 0
    reasons = []

    # 1. 战术评分映射
    if tactical_score >= 85: tactical_mult = 2.0; reasons.append("战术:极强")
    elif tactical_score >= 70: tactical_mult = 1.0; reasons.append("战术:走强")
    elif tactical_score >= 60: tactical_mult = 0.5; reasons.append("战术:企稳")
    elif tactical_score <= 25: tactical_mult = -1.0; reasons.append("战术:破位")

    # 2. 战略估值修正
    final_mult = tactical_mult
    if tactical_mult > 0:
        if val_mult < 0.5: final_mult = 0; reasons.append(f"战略:高估刹车")
        elif val_mult > 1.0: final_mult *= val_mult; reasons.append(f"战略:低估加倍")
    elif tactical_mult < 0:
        if val_mult > 1.2: final_mult = 0; reasons.append(f"战略:底部锁仓")
        elif val_mult < 0.8: final_mult *= 1.5; reasons.append("战略:高估止损")
    else:
        if val_mult >= 1.5 and strategy_type in ['core', 'dividend']:
            final_mult = 0.5; reasons.append(f"战略:左侧定投")

    # 3. 风控一票否决
    if cro_signal == "VETO" and final_mult > 0:
        final_mult = 0; reasons.append(f"🛡️风控:否决")
    
    # 4. 交易规则
    held_days = pos.get('held_days', 999)
    if final_mult < 0 and pos['shares'] > 0 and held_days < 7:
        final_mult = 0; reasons.append(f"规则:锁仓({held_days}天)")

    final_amt = 0; is_sell = False; sell_val = 0; label = "观望"
    if final_mult > 0:
        final_amt = max(0, min(int(base_amt * final_mult), int(max_daily)))
        label = "买入"
    elif final_mult < 0:
        is_sell = True
        sell_val = pos['shares'] * tech.get('price', 0) * min(abs(final_mult), 1.0)
        label = "卖出"

    if reasons: tech['quant_reasons'] = reasons
    return final_amt, label, is_sell, sell_val

def process_single_fund(fund, config, fetcher, tracker, val_engine, analyst, market_context, base_amt, max_daily):
    """单只基金全流程处理"""
    
    # 强制随机延时 (防封锁)
    time.sleep(random.uniform(2.0, 4.0))
    
    try:
        # 1. 获取数据
        data = fetcher.get_fund_history(fund['code'])
        if data is None or data.empty: return None, "", []
        
        # 2. 技术分析 (V17.0)
        # 注意：需要确保 technical_analyzer.py 已更新为最新版 (含 __init__)
        analyzer_instance = TechnicalAnalyzer(asset_type='ETF') 
        tech = analyzer_instance.calculate_indicators(data)
        if not tech: return None, []
        
        # 3. 估值分析
        val_mult, val_desc = val_engine.get_valuation_status(
            fund.get('index_name'), 
            fund.get('strategy_type'), 
            fund.get('code') 
        )
        with tracker_lock: pos = tracker.get_position(fund['code'])

        # 4. AI 投委会分析
        ai_res = {}
        if analyst:
            cro_signal = tech.get('tech_cro_signal', 'PASS')
            risk_payload = {"fuse_level": 3 if cro_signal == 'VETO' else 0, "risk_msg": tech.get('tech_cro_comment', '监控')}
            ai_res = analyst.analyze_fund_v5(fund['name'], tech, None, market_context, risk_payload, fund.get('strategy_type', 'core'))

        ai_adj = ai_res.get('adjustment', 0)
        ai_decision = ai_res.get('decision', 'PASS') 
        
        # 5. 计算最终仓位
        amt, lbl, is_sell, s_val = calculate_position_v13(tech, ai_adj, ai_decision, val_mult, val_desc, base_amt, max_daily, pos, fund.get('strategy_type'), fund['name'])
        
        # 6. 记账
        with tracker_lock:
            tracker.record_signal(fund['code'], lbl)
            if amt > 0: tracker.add_trade(fund['code'], fund['name'], amt, tech['price'])
            elif is_sell: tracker.add_trade(fund['code'], fund['name'], s_val, tech['price'], True)

        cio_log = f"标的:{fund['name']} | 阶段:{ai_res.get('trend_analysis',{}).get('stage','-')} | 决策:{lbl}"
        return {"name": fund['name'], "code": fund['code'], "amount": amt, "sell_value": s_val, "is_sell": is_sell, "tech": tech, "ai_analysis": ai_res}, cio_log, []
    except Exception as e:
        logger.error(f"Error {fund['name']}: {e}", exc_info=True); return None, "", []

def main():
    config = load_config()
    fetcher, tracker, val_engine = DataFetcher(), PortfolioTracker(), ValuationEngine()
    
    tracker.confirm_trades()
    
    try: analyst = NewsAnalyst()
    except: analyst = None

    market_context = analyst.get_market_context() if analyst else "无数据"
    all_news_seen = [line.strip() for line in market_context.split('\n') if line.strip().startswith('[')]

    # --- 标的列表处理逻辑 ---
    funds = config.get('funds', [])
    
    if TEST_MODE:
        if funds:
            logger.info(f"🚧 【测试模式开启】仅处理第一个标的: {funds[0]['name']}")
            funds = funds[:1] # 只取切片中的第一个
        else:
            logger.error("❌ Config 中没有基金，无法测试")
            return

    results, cio_lines = [], []
    
    logger.info("🚀 启动单线程处理...")
    
    # 无论是否测试模式，都强制单线程，确保稳定
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(process_single_fund, f, config, fetcher, tracker, val_engine, analyst, market_context, config['global']['base_invest_amount'], config['global']['max_daily_invest']): f for f in funds}
        for f in as_completed(futures):
            res, log, _ = f.result()
            if res: 
                results.append(res); cio_lines.append(log)
                print(f"✅ 完成: {res['name']}") 

    if results:
        results.sort(key=lambda x: -x['tech'].get('final_score', 0))
        full_report = "\n".join(cio_lines)
        cio_html = analyst.review_report(full_report, market_context) if analyst else ""
        advisor_html = analyst.advisor_review(full_report, market_context) if analyst else ""
        
        # 调用分离出去的 UI 渲染器
        html = render_html_report_v17(all_news_seen, results, cio_html, advisor_html) 
        
        subject_prefix = "🚧 [测试] " if TEST_MODE else "🕊️ "
        send_email(f"{subject_prefix}鹊知风 V17.0 全量化仪表盘", html, attachment_path=LOG_FILENAME)
        logger.info("✅ 测试运行结束，邮件已发送。")
    else:
        logger.warning("⚠️ 没有生成任何结果，请检查日志报错。")

if __name__ == "__main__": main()
