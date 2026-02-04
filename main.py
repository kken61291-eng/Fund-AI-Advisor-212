import yaml
import os
import time
from datetime import datetime
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
from market_scanner import MarketScanner
from technical_analyzer import TechnicalAnalyzer
from portfolio_tracker import PortfolioTracker
from utils import send_email, logger

def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def calculate_position(tech_data, base_amount, max_daily, pos_info, strategy_type):
    # --- 核心算法逻辑保持 V10 标准 ---
    score = tech_data['quant_score']
    weekly = tech_data['trend_weekly']
    
    shares = pos_info['shares']
    held_days = pos_info.get('held_days', 999)
    
    is_core = (strategy_type == 'core')
    multiplier = 0
    reasons = []

    # 评分系统
    if score >= 85: 
        multiplier = 2.0; reasons.append("极高分")
    elif score >= 70: 
        multiplier = 1.0
    elif score >= 60: 
        multiplier = 0.5
    elif score <= 15: 
        multiplier = -1.0 
    
    # 策略微调
    if is_core:
        if multiplier < 0 and score > -40: multiplier = 0 
        if weekly == "UP" and multiplier == 0: multiplier = 0.5

    if not is_core:
        cost = pos_info['cost']
        if shares > 0:
            pct = (tech_data['price'] - cost) / cost * 100
            if pct > 15 and score < 70: multiplier = -0.5 
            if pct < -8 and score < 40: multiplier = -1.0 

    # 七日锁
    if multiplier < 0 and shares > 0 and held_days < 7: 
        multiplier = 0; reasons.append(f"锁仓({held_days}天)")

    # 熊市防御
    if weekly == "DOWN":
        if multiplier > 0: multiplier *= 0.5 
        if is_core and multiplier < 0 and score > -60: multiplier = 0 

    final_amount = 0
    is_sell = False
    sell_value = 0
    label = "观望"

    if multiplier > 0:
        final_amount = max(0, min(int(base_amount * multiplier), int(max_daily)))
        label = "买入"
    elif multiplier < 0:
        is_sell = True
        sell_ratio = min(abs(multiplier), 1.0)
        sell_value = shares * tech_data['price'] * sell_ratio
        label = "卖出"

    # [修复] 必须确保 quant_reasons 存在
    if reasons:
        if 'quant_reasons' not in tech_data: tech_data['quant_reasons'] = []
        tech_data['quant_reasons'].extend(reasons)
        
    return final_amount, label, is_sell, sell_value

def render_html_report(market_ctx, funds_results, daily_total_cap, cio_review):
    # --- UI 渲染 ---
    def render_dots(hist):
        h = ""
        for x in hist:
            c = "#ff4d4f" if x['s']=='B' else ("#52c41a" if x['s'] in ['S','C'] else "#444")
            h += f'<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:{c};margin-right:3px;" title="{x["date"]}"></span>'
        return h

    rows = ""
    for r in funds_results:
        color = "#ff4d4f" if r['amount'] > 0 else ("#52c41a" if r.get('is_sell') else "#444")
        act = f"+{r['amount']:,}" if r['amount']>0 else (f"-{int(r.get('sell_value',0)):,}" if r.get('is_sell') else "HOLD")
        
        # 安全获取字段
        reasons = " ".join([f"[{x}]" for x in r['tech'].get('quant_reasons', [])])
        
        ai_txt = ""
        if r.get('ai_analysis') and r['ai_analysis'].get('comment'):
            ai_txt = f"""
            <div style='font-size:12px;color:#aaa;margin-top:8px;border-top:1px dashed #333;padding-top:5px;line-height:1.4;'>
                <span style='color:#D4AF37'>🤖 洞察:</span> {r['ai_analysis'].get('comment')}
                <div style='margin-top:2px;'><span style='color:#ff4d4f'>⚠️ 风险:</span> {r['ai_analysis'].get('risk_alert')}</div>
            </div>
            """

        rows += f"""
        <div style="background:#222;border-left:4px solid {color};margin-bottom:12px;padding:12px;border-radius:6px;box-shadow:0 2px 4px rgba(0,0,0,0.2);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <div>
                    <span style="font-size:16px;font-weight:bold;color:#fff;">{r['name']}</span>
                    <span style="font-size:12px;color:#888;margin-left:5px;">{r['code']}</span>
                </div>
                <div style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold;font-size:12px;">{r['tech']['quant_score']}分</div>
            </div>
            
            <div style="display:flex;justify-content:space-between;color:#ddd;font-size:14px;margin-bottom:5px;">
                <span style="font-weight:bold;">{r['position_type']}</span>
                <span style="font-family:monospace;">{act}</span>
            </div>
            
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;font-size:11px;color:#888;font-family:monospace;margin-bottom:5px;">
                <span>RSI: {r['tech']['rsi']}</span>
                <span>MACD: {r['tech']['macd']['trend']}</span>
                <span>OBV: {'流入' if r['tech']['flow']['obv_slope']>0 else '流出'}</span>
                <span>周线: {r['tech']['trend_weekly']}</span>
            </div>
            
            <div style="font-size:10px;color:#D4AF37;">{reasons}</div>
            <div style="margin-top:5px;">{render_dots(r.get('history',[]))}</div>
            {ai_txt}
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html><body style="background:#121212;color:#e0e0e0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:640px;margin:0 auto;padding:15px;">
        <div style="text-align:center;border-bottom:2px solid #D4AF37;padding-bottom:15px;margin-bottom:20px;">
            <h2 style="color:#D4AF37;margin:0;letter-spacing:1px;">鎏金量化 V10.9</h2>
            <div style="font-size:11px;color:#666;margin-top:5px;text-transform:uppercase;">Deep Analysis Edition | {datetime.now().strftime('%Y-%m-%d')}</div>
            <div style="font-size:12px;color:#aaa;margin-top:5px;">宏观情绪: {market_ctx.get('north_label')}</div>
        </div>
        
        <div style="background:#1a1a1a;padding:15px;border:1px solid #444;border-radius:8px;margin-bottom:20px;font-size:13px;line-height:1.5;">
            {cio_review}
        </div>
        
        {rows}
        
        <div style="text-align:center;font-size:10px;color:#444;margin-top:30px;">
            SYSTEM V10.9 | POWERED BY KIMI & YAHOO FINANCE
        </div>
    </body></html>
    """

def main():
    config = load_config()
    fetcher = DataFetcher()
    scanner = MarketScanner()
    tracker = PortfolioTracker() 
    
    logger.info(">>> [V10.9] 启动深度分析模式 (Quality First)...")
    tracker.confirm_trades()
    
    try: analyst = NewsAnalyst()
    except: analyst = None

    market_ctx = scanner.get_market_sentiment()
    funds_results = []
    
    # 收集详细信息给 CIO
    cio_summary_lines = [f"市场环境: {market_ctx}"]
    
    BASE_AMT = config['global']['base_invest_amount']
    MAX_DAILY = config['global']['max_daily_invest']

    for fund in config['funds']:
        try:
            logger.info(f"Analyzing {fund['name']}...")
            data = fetcher.get_fund_history(fund['code'])
            if not data: continue

            tech = TechnicalAnalyzer.calculate_indicators(data)
            if not tech: continue

            pos = tracker.get_position(fund['code'])
            amt, lbl, is_sell, s_val = calculate_position(tech, BASE_AMT, MAX_DAILY, pos, fund.get('strategy_type'))
            
            tracker.record_signal(fund['code'], lbl)
            
            # [深度分析] 只要有持仓或有操作，或评分有异动，就强制 AI 介入
            # V10.9 降低 AI 触发门槛，确保重要标的都有点评
            ai_res = {}
            need_ai = (amt > 0) or is_sell or (tech['quant_score'] >= 65) or (tech['quant_score'] <= 35) or (pos['shares'] > 0)
            
            if analyst and need_ai:
                news = analyst.fetch_news_titles(fund['sector_keyword'])
                ai_res = analyst.analyze_fund_v4(fund['name'], tech, market_ctx, news)

            if amt > 0: tracker.add_trade(fund['code'], fund['name'], amt, tech['price'])
            elif is_sell: tracker.add_trade(fund['code'], fund['name'], s_val, tech['price'], True)

            # 构建详细的 CIO 汇报行
            act_str = f"买入{amt}" if amt>0 else ("卖出" if is_sell else "持有/观望")
            cio_summary_lines.append(f"- {fund['name']}: {act_str} (分:{tech['quant_score']}, RSI:{tech['rsi']}, OBV:{tech['flow']['obv_slope']})")

            funds_results.append({
                "name": fund['name'], "code": fund['code'], "amount": amt, "sell_value": s_val,
                "position_type": lbl, "is_sell": is_sell, "tech": tech, "ai_analysis": ai_res, 
                "history": tracker.get_signal_history(fund['code'])
            })
            
            # Yahoo 速度很快，不需要长 sleep，0.2秒缓冲足矣
            time.sleep(0.2) 

        except Exception as e:
            logger.error(f"Err {fund['name']}: {e}")

    cio_review = ""
    if analyst and funds_results:
        logger.info(">>> CIO Deep Audit...")
        # 发送完整的汇报清单
        cio_review = analyst.review_report("\n".join(cio_summary_lines))

    if funds_results:
        funds_results.sort(key=lambda x: -x['tech']['quant_score'])
        html = render_html_report(market_ctx, funds_results, MAX_DAILY, cio_review)
        send_email("📊 鎏金量化 V10.9 深度战报", html)

if __name__ == "__main__":
    main()
