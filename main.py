import yaml
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
from market_scanner import MarketScanner
from technical_analyzer import TechnicalAnalyzer
from valuation_engine import ValuationEngine
from portfolio_tracker import PortfolioTracker
from utils import send_email, logger, LOG_FILENAME

# --- 全局配置 ---
DEBUG_MODE = True  
tracker_lock = threading.Lock()

def load_config():
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"配置文件读取失败: {e}")
        return {"funds": [], "global": {"base_invest_amount": 1000, "max_daily_invest": 5000}}

def calculate_position_v13(tech, ai_adj, val_mult, val_desc, base_amt, max_daily, pos, strategy_type, fund_name):
    # ... (保持原有的 calculate_position_v13 逻辑完全不变) ...
    # 为节省篇幅，此处省略具体的算分逻辑代码，请保留之前版本的内容
    # 核心逻辑与之前完全一致
    base_score = tech.get('quant_score', 50)
    if DEBUG_MODE:
        logger.info(f"🔍 [DEBUG] {fund_name} 基础分细节: {tech.get('quant_reasons', [])}")

    tactical_score = max(0, min(100, base_score + ai_adj))
    action_str = "加分进攻" if ai_adj > 0 else ("减分防御" if ai_adj < 0 else "中性维持")
    logger.info(f"🧮 [算分 {fund_name}] 技术面({base_score}) + CIO修正({ai_adj:+d} {action_str}) = 最终分({tactical_score})")
    
    tech['final_score'] = tactical_score
    tech['ai_adjustment'] = ai_adj
    tech['valuation_desc'] = val_desc
    cro_signal = tech.get('tech_cro_signal', 'PASS')
    
    tactical_mult = 0
    reasons = []

    if tactical_score >= 85: tactical_mult = 2.0; reasons.append("战术:极强")
    elif tactical_score >= 70: tactical_mult = 1.0; reasons.append("战术:走强")
    elif tactical_score >= 60: tactical_mult = 0.5; reasons.append("战术:企稳")
    elif tactical_score <= 25: tactical_mult = -1.0; reasons.append("战术:破位")

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

    if cro_signal == "VETO":
        if final_mult > 0:
            final_mult = 0
            reasons.append(f"🛡️风控:否决买入")
            logger.info(f"🚫 [风控拦截 {fund_name}] 触发: {tech.get('tech_cro_comment')}")
    
    held_days = pos.get('held_days', 999)
    if final_mult < 0 and pos['shares'] > 0 and held_days < 7:
        final_mult = 0; reasons.append(f"规则:锁仓({held_days}天)")

    final_amt = 0; is_sell = False; sell_val = 0; label = "观望"
    if final_mult > 0:
        amt = int(base_amt * final_mult)
        final_amt = max(0, min(amt, int(max_daily)))
        label = "买入"
    elif final_mult < 0:
        is_sell = True
        sell_ratio = min(abs(final_mult), 1.0)
        sell_val = pos['shares'] * tech.get('price', 0) * sell_ratio
        label = "卖出"

    if reasons: tech['quant_reasons'] = reasons
    return final_amt, label, is_sell, sell_val

def process_single_fund(fund, config, fetcher, scanner, tracker, val_engine, analyst, macro_str, base_amt, max_daily):
    res = None
    cio_log = ""
    used_news = []
    
    try:
        logger.info(f"Analyzing {fund['name']}...")
        
        # [修改] 这里调用 get_fund_history，它现在会直接读取本地文件
        data = fetcher.get_fund_history(fund['code'])
        if data is None or data.empty: 
            # 如果本地没文件，说明 batch_updater 没跑或者失败了
            logger.warning(f"⚠️ 缓存缺失: {fund['name']} (请检查 data_cache 目录)")
            return None, "", []

        tech = TechnicalAnalyzer.calculate_indicators(data)
        if not tech: return None, "", []
        
        logger.info(f"📊 [Hard Data {fund['name']}] RSI:{tech.get('rsi')} | VR:{tech.get('risk_factors',{}).get('vol_ratio')}")

        try:
            val_mult, val_desc = val_engine.get_valuation_status(fund.get('index_name'), fund.get('strategy_type'))
        except:
            val_mult, val_desc = 1.0, "估值异常"

        with tracker_lock: pos = tracker.get_position(fund['code'])

        ai_adj = 0; ai_res = {}
        keyword = fund.get('sector_keyword', fund['name']) 
        
        # [V15.6] 强制AI分析逻辑
        should_run_ai = (
            pos['shares'] > 0 
            or tech['quant_score'] >= 60 
            or tech['quant_score'] <= 35 
            or DEBUG_MODE 
        )

        if analyst and should_run_ai:
            sector_news_list = analyst.fetch_news_titles(keyword)
            logger.info(f"📰 [News Source] {fund['name']}: Found {len(sector_news_list)} articles")
            
            cro_signal = tech.get('tech_cro_signal', 'PASS')
            fuse_level = 0
            if cro_signal == 'VETO': fuse_level = 3
            elif cro_signal == 'WARN': fuse_level = 1
            
            risk_payload = {
                "fuse_level": fuse_level,
                "risk_msg": tech.get('tech_cro_comment', '常规监控')
            }
            
            try:
                ai_res = analyst.analyze_fund_v5(fund['name'], tech, macro_str, sector_news_list, risk_payload)
                ai_adj = ai_res.get('adjustment', 0)
            except Exception as ai_e:
                logger.error(f"❌ AI Analysis Failed for {fund['name']}: {ai_e}")
                ai_res = {"bull_view": "系统故障", "bear_view": "请检查日志", "comment": "AI离线", "adjustment": 0}
            
            for n_str in sector_news_list:
                if "]" in n_str:
                    t_part, title_part = n_str.split("]", 1)
                    used_news.append({"title": title_part.strip(), "time": t_part.replace("[", "").strip()})
                else:
                    used_news.append({"title": n_str, "time": ""})

        amt, lbl, is_sell, s_val = calculate_position_v13(
            tech, ai_adj, val_mult, val_desc, base_amt, max_daily, pos, fund.get('strategy_type'), fund['name']
        )
        
        with tracker_lock:
            tracker.record_signal(fund['code'], lbl)
            if amt > 0: tracker.add_trade(fund['code'], fund['name'], amt, tech['price'])
            elif is_sell: tracker.add_trade(fund['code'], fund['name'], s_val, tech['price'], True)

        bull = ai_res.get('bull_view') or ai_res.get('bull_say', '无')
        bear = ai_res.get('bear_view') or ai_res.get('bear_say', '无')
        
        if bull != '无' or bear != '无':
            logger.info(f"🗣️ [投委会 {fund['name']}]\n   🦊 CGO: {bull}\n   🐻 CRO: {bear}")

        cio_log = f"""
【{fund['name']}】: {lbl}
- 算分: 基础{tech.get('quant_score')} + CIO修正{ai_adj:+d} = {tech.get('final_score')}
- 风控: {tech.get('tech_cro_comment', '无')}
- 辩论: 多方<{bull}> vs 空方<{bear}>
"""
        res = {
            "name": fund['name'], "code": fund['code'], 
            "amount": amt, "sell_value": s_val, "position_type": lbl, "is_sell": is_sell, 
            "tech": tech, "ai_analysis": ai_res, "history": tracker.get_signal_history(fund['code']),
            "pos_cost": pos.get('cost', 0), "pos_shares": pos.get('shares', 0)
        }
    except Exception as e:
        logger.error(f"Process Error {fund['name']}: {e}")
        if DEBUG_MODE: logger.exception(e)
        return None, "", []
    return res, cio_log, used_news

def render_html_report_v13(all_news, results, cio_html, advisor_html):
    # ... (保持原有的 UI 渲染逻辑不变，篇幅原因省略，请直接保留您现有的 render_html_report_v13 函数) ...
    # 请务必保留之前的 HTML 渲染代码
    return f"""<!DOCTYPE html><html><body><h1>Reports Generated</h1></body></html>"""

def main():
    config = load_config()
    fetcher = DataFetcher()
    scanner = MarketScanner()
    tracker = PortfolioTracker()
    val_engine = ValuationEngine()
    
    logger.info(f">>> [V15.13] Startup | LOCAL_MODE=True | Reading from ./data_cache/")
    tracker.confirm_trades()
    try: analyst = NewsAnalyst()
    except: analyst = None

    macro_news_list = scanner.get_macro_news()
    macro_str = " | ".join([n['title'] for n in macro_news_list])
    
    all_news_seen = []
    for n in macro_news_list:
        all_news_seen.append(n)

    results = []; cio_lines = [f"【宏观环境】: {macro_str}\n"]
    
    # [修改] 既然是读本地文件，IO速度极快，并发可以开大一点，比如 5 或者 10
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_fund = {executor.submit(
            process_single_fund, 
            fund, config, fetcher, scanner, tracker, val_engine, analyst, macro_str, 
            config['global']['base_invest_amount'], config['global']['max_daily_invest']
        ): fund for fund in config.get('funds', [])}
        
        for future in as_completed(future_to_fund):
            try:
                res, log, fund_news = future.result()
                if res: 
                    results.append(res)
                    cio_lines.append(log)
                    all_news_seen.extend(fund_news)
            except Exception as e: logger.error(f"Thread Error: {e}")

    if results:
        results.sort(key=lambda x: -x['tech'].get('final_score', 0))
        full_report = "\n".join(cio_lines)
        
        cio_html = analyst.review_report(full_report, macro_str) if analyst else "<p>CIO Missing</p>"
        advisor_html = analyst.advisor_review(full_report, macro_str) if analyst else "<p>Advisor Offline</p>"
        
        # 使用 utils.py 里的 render 逻辑 (这里假设您会保留原有的 UI 代码)
        from main import render_html_report_v13 as original_render # 临时指代
        
        # 注意：这里需要把上面省略的 render_html_report_v13 补全，或者确保您本地有这个函数
        # 为了演示，我假设您已经有了
        html = render_html_report_v13(all_news_seen, results, cio_html, advisor_html) 
        
        send_email("🗡️ 玄铁量化 V15.13 铁拳决议 (Local Mode)", html, attachment_path=LOG_FILENAME)

if __name__ == "__main__": main()
