import yaml
import os
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
from market_scanner import MarketScanner
from technical_analyzer import TechnicalAnalyzer
from valuation_engine import ValuationEngine
from portfolio_tracker import PortfolioTracker
from utils import send_email, logger

tracker_lock = threading.Lock()

def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# [V13.0 决策逻辑保持不变]
def calculate_position_v13(tech, ai_adj, val_mult, val_desc, base_amt, max_daily, pos, strategy_type):
    base_score = tech.get('quant_score', 50)
    tactical_score = max(0, min(100, base_score + ai_adj))
    
    tech['final_score'] = tactical_score
    tech['ai_adjustment'] = ai_adj
    tech['valuation_desc'] = val_desc
    
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

    held_days = pos.get('held_days', 999)
    if final_mult < 0 and pos['shares'] > 0 and held_days < 7:
        final_mult = 0; reasons.append(f"风控:锁仓({held_days}天)")

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

# [V13.7 UI 升级] 增加持仓收益 + 风险提示
def render_html_report_v13(macro_list, results, cio, advisor):
    macro_html = ""
    for news in macro_list:
        macro_html += f"""
        <div style="font-size:12px;color:#eeeeee;margin-bottom:6px;border-bottom:1px dashed #5d4037;padding-bottom:4px;line-height:1.4;">
            <span style="color:#ffb74d;margin-right:5px;font-weight:bold;">●</span>{news.get('title','')} 
            <span style="color:#bdbdbd;float:right;font-size:10px;">[{news.get('source','')}]</span>
        </div>
        """

    def render_dots(hist):
        h = ""
        for x in hist:
            c = "#d32f2f" if x['s']=='B' else ("#388e3c" if x['s'] in ['S','C'] else "#555")
            h += f'<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:{c};margin-right:3px;box-shadow:0 0 2px rgba(0,0,0,0.5);" title="{x["date"]}"></span>'
        return h

    rows = ""
    for r in results:
        try:
            tech = r.get('tech', {})
            risk = tech.get('risk_factors', {})
            final_score = tech.get('final_score', 0)
            
            # --- [V13.7] 计算持仓收益 ---
            profit_html = ""
            pos_cost = r.get('pos_cost', 0.0)
            pos_shares = r.get('pos_shares', 0)
            current_price = tech.get('price', 0.0)
            
            if pos_shares > 0 and pos_cost > 0 and current_price > 0:
                profit_pct = (current_price - pos_cost) / pos_cost * 100
                profit_val = (current_price - pos_cost) * pos_shares
                
                # A股风格：红涨绿跌
                p_color = "#ff5252" if profit_val > 0 else "#69f0ae" 
                profit_html = f"""
                <div style="font-size:12px;margin-bottom:8px;background:rgba(255,255,255,0.05);padding:4px 8px;border-radius:3px;display:flex;justify-content:space-between;">
                    <span style="color:#aaa;">持有收益:</span>
                    <span style="color:{p_color};font-weight:bold;">{profit_val:+.1f}元 ({profit_pct:+.2f}%)</span>
                </div>
                """
            
            # 配色逻辑
            if r['amount'] > 0: 
                border_color = "#d32f2f"
                bg_gradient = "linear-gradient(90deg, rgba(60,10,10,0.9) 0%, rgba(20,20,20,0.95) 100%)"
                act_html = f"<span style='color:#ff8a80;font-weight:bold'>+{r['amount']:,}</span>"
            elif r.get('is_sell'): 
                border_color = "#388e3c"
                bg_gradient = "linear-gradient(90deg, rgba(10,40,10,0.9) 0%, rgba(20,20,20,0.95) 100%)"
                act_html = f"<span style='color:#a5d6a7;font-weight:bold'>-{int(r.get('sell_value',0)):,}</span>"
            else: 
                border_color = "#555"
                bg_gradient = "linear-gradient(90deg, rgba(30,30,30,0.9) 0%, rgba(15,15,15,0.95) 100%)"
                act_html = "<span style='color:#777'>HOLD</span>"
            
            reasons = " ".join([f"<span style='border:1px solid #555;padding:0 3px;font-size:9px;border-radius:2px;color:#888;'>{x}</span>" for x in tech.get('quant_reasons', [])])
            
            val_desc = tech.get('valuation_desc', 'N/A')
            if "低估" in val_desc or "机会" in val_desc: val_style = "color:#ffb74d;font-weight:bold;"
            elif "高估" in val_desc or "泡沫" in val_desc: val_style = "color:#ef5350;font-weight:bold;"
            else: val_style = "color:#bdbdbd;"

            # AI 点评 + [V13.7] 风险提示
            ai_txt = ""
            ai_data = r.get('ai_analysis', {})
            if ai_data.get('comment'):
                # 风险提示部分
                risk_alert_html = ""
                if ai_data.get('risk_alert') and ai_data.get('risk_alert') != "无":
                     risk_alert_html = f"<div style='margin-top:4px;color:#ef5350;font-size:11px;'><strong>⚡ 警示:</strong> {ai_data['risk_alert']}</div>"
                
                ai_txt = f"""
                <div style='font-size:12px;color:#d7ccc8;margin-top:10px;padding:8px;background:rgba(0,0,0,0.3);border-radius:4px;border-left:2px solid #ffb74d;'>
                    <div style='margin-bottom:4px;'><strong style='color:#ffb74d'>✦ 洞察:</strong> {ai_data.get('comment')}</div>
                    {risk_alert_html}
                </div>
                """

            vol_ratio = risk.get('vol_ratio', 1.0)
            div = risk.get('divergence', '无')
            vol_style = "color:#ffb74d;" if vol_ratio < 0.8 else ("color:#ff8a80;" if vol_ratio > 2.0 else "color:#bbb;")
            div_style = "color:#ef5350;font-weight:bold;" if "顶背离" in str(div) else ("color:#a5d6a7;" if "底背离" in str(div) else "color:#bbb;")

            rows += f"""
            <div style="background:{bg_gradient};border-left:4px solid {border_color};margin-bottom:15px;padding:15px;border-radius:6px;box-shadow:0 4px 10px rgba(0,0,0,0.6);border-top:1px solid #333;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                    <div>
                        <span style="font-size:18px;font-weight:bold;color:#f0e6d2;font-family:'Times New Roman',serif;">{r['name']}</span>
                        <span style="font-size:12px;color:#9ca3af;margin-left:5px;">{r['code']}</span>
                    </div>
                    <div style="text-align:right;">
                        <div style="color:#ffb74d;font-weight:bold;font-size:16px;text-shadow:0 0 5px rgba(255,183,77,0.3);">{final_score}</div>
                        <div style="font-size:9px;color:#666;">XUANTIE SCORE</div>
                    </div>
                </div>
                
                <div style="display:flex;justify-content:space-between;color:#e0e0e0;font-size:15px;margin-bottom:5px;border-bottom:1px solid #444;padding-bottom:5px;">
                    <span style="font-weight:bold;color:#ffb74d;">{r.get('position_type')}</span>
                    <span style="font-family:'Courier New',monospace;">{act_html}</span>
                </div>
                
                {profit_html}

                <div style="font-size:11px;margin-bottom:8px;border-bottom:1px dashed #333;padding-bottom:5px;">
                     <span style="color:#888;">周期定位:</span> <span style="{val_style}">{val_desc}</span>
                </div>

                <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:5px;font-size:11px;color:#bdbdbd;font-family:'Courier New',monospace;margin-bottom:4px;">
                    <span>RSI: {tech.get('rsi','-')}</span>
                    <span>MACD: {tech.get('macd',{}).get('trend','-')}</span>
                    <span>OBV: {'流入' if tech.get('flow',{}).get('obv_slope',0)>0 else '流出'}</span>
                    <span>Wkly: {tech.get('trend_weekly','-')}</span>
                </div>
                
                <div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:5px;font-size:11px;color:#bdbdbd;font-family:'Courier New',monospace;margin-bottom:8px;">
                    <span style="{vol_style}">VR: {vol_ratio}</span>
                    <span style="{div_style}">Div: {div}</span>
                    <span>%B: {risk.get('bollinger_pct_b',0.5)}</span>
                </div>

                <div style="margin-bottom:8px;">{reasons}</div>
                <div style="margin-top:5px;">{render_dots(r.get('history',[]))}</div>
                {ai_txt}
            </div>
            """
        except Exception as e:
            logger.error(f"渲染错误 {r.get('name')}: {e}")

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        body {{ 
            background: #0a0a0a;
            color: #f0e6d2; 
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; 
            max-width: 660px; margin: 0 auto; padding: 20px;
        }}
        .main-container {{
            border: 2px solid #3e2723;
            border-top: 5px solid #ffb74d;
            border-radius: 4px;
            padding: 20px;
            background: linear-gradient(180deg, #1b1b1b 0%, #000000 100%);
            box-shadow: 0 10px 30px rgba(0,0,0,0.8);
        }}
        .header {{ text-align: center; border-bottom: 2px solid #3e2723; padding-bottom: 20px; margin-bottom: 25px; }}
        .title {{ 
            color: #ffb74d; margin: 0; font-size: 32px; letter-spacing: 3px; font-weight: 800; 
            text-transform: uppercase; font-family: 'Times New Roman', serif;
            text-shadow: 0 2px 10px rgba(0,0,0,0.9);
            background: -webkit-linear-gradient(#fff, #ffb74d); -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        .subtitle {{ font-size: 11px; color: #8d6e63; margin-top: 8px; letter-spacing: 2px; text-transform: uppercase; }}
        
        .macro-panel {{
            background: rgba(30, 30, 30, 0.6); 
            border: 1px solid #3e2723;
            border-radius: 4px;
            padding: 15px;
            margin-top: 20px;
            text-align: left;
        }}
        
        .cio-paper {{ 
            background: #121212; padding: 20px; border: 1px solid #3e2723; border-radius: 2px; 
            margin-bottom: 25px; font-size: 14px; line-height: 1.6; color: #d7ccc8;
            box-shadow: inset 0 0 30px rgba(0,0,0,0.8); position: relative;
        }}
        .cio-seal {{
            position: absolute; top: 10px; right: 10px; 
            border: 2px solid #ffb74d; color: #ffb74d;
            padding: 5px 15px; font-size: 14px; 
            transform: rotate(-10deg); font-weight: 900; 
            opacity: 0.9; 
            text-shadow: 0 0 10px rgba(255, 183, 77, 0.2);
            letter-spacing: 2px;
        }}
        
        .advisor-paper {{
            background: #1a1a1a; 
            border-left: 4px solid #5d4037; 
            padding: 20px; 
            margin-bottom: 25px; 
            font-size: 14px; line-height: 1.6; color: #e0e0e0;
            background-image: repeating-linear-gradient(45deg, rgba(255,255,255,0.02) 0px, rgba(255,255,255,0.02) 1px, transparent 1px, transparent 5px);
        }}

        .footer {{ text-align: center; font-size: 10px; color: #4e342e; margin-top: 40px; font-family: serif; }}
    </style>
    </head>
    <body>
        <div class="main-container">
            <div class="header">
                <h1 class="title">XUANTIE QUANT</h1>
                <div class="subtitle">HEAVY SWORD, NO EDGE | V13.7 CLASSIC REVIVAL</div>
                
                <div class="macro-panel">
                    <div style="font-size:11px;color:#ffb74d;margin-bottom:10px;text-transform:uppercase;border-bottom:1px solid #333;padding-bottom:4px;">Global Macro Radar</div>
                    {macro_html}
                </div>
            </div>
            
            <div class="cio-paper">
                <div class="cio-seal">CIO APPROVED</div>
                {cio}
            </div>
            
            <div class="advisor-paper">
                {advisor}
            </div>
            
            {rows}
            
            <div class="footer">
                EST. 2026 | POWERED BY CAILIAN & JINSHI DATA <br>
                "In Math We Trust, By AI We Verify."
            </div>
        </div>
    </body></html>
    """

def process_single_fund(fund, config, fetcher, scanner, tracker, val_engine, analyst, macro_str, base_amt, max_daily):
    res = None
    cio_log = ""
    try:
        time.sleep(random.uniform(0.5, 2.5)) 
        logger.info(f"Analyzing {fund['name']}...")
        
        data = fetcher.get_fund_history(fund['code'])
        if not data: return None, f"数据失败: {fund['name']}"

        tech = TechnicalAnalyzer.calculate_indicators(data)
        if not tech: return None, f"指标失败: {fund['name']}"

        try:
            val_mult, val_desc = val_engine.get_valuation_status(fund.get('index_name'), fund.get('strategy_type'))
        except:
            val_mult, val_desc = 1.0, "估值异常"

        # [V13.7] 获取持仓数据传递给渲染函数
        with tracker_lock: pos = tracker.get_position(fund['code'])

        ai_adj = 0; ai_res = {}
        if analyst and (pos['shares']>0 or tech['quant_score']>=60 or tech['quant_score']<=35):
            news = analyst.fetch_news_titles(fund['sector_keyword'])
            ai_res = analyst.analyze_fund_v4(fund['name'], tech, macro_str, news)
            ai_adj = ai_res.get('adjustment', 0)

        amt, lbl, is_sell, s_val = calculate_position_v13(tech, ai_adj, val_mult, val_desc, base_amt, max_daily, pos, fund.get('strategy_type'))
        
        with tracker_lock:
            tracker.record_signal(fund['code'], lbl)
            if amt > 0: tracker.add_trade(fund['code'], fund['name'], amt, tech['price'])
            elif is_sell: tracker.add_trade(fund['code'], fund['name'], s_val, tech['price'], True)

        cio_log = f"- {fund['name']}: {lbl} ({val_desc})"
        res = {
            "name": fund['name'], "code": fund['code'], 
            "amount": amt, "sell_value": s_val, "position_type": lbl, "is_sell": is_sell, 
            "tech": tech, "ai_analysis": ai_res, "history": tracker.get_signal_history(fund['code']),
            "pos_cost": pos.get('cost', 0), "pos_shares": pos.get('shares', 0) # [V13.7 新增] 传递成本数据
        }
        
    except Exception as e:
        logger.error(f"处理错误 {fund['name']}: {e}")
        return None, f"Error {fund['name']}: {e}"
    return res, cio_log

def main():
    config = load_config()
    fetcher = DataFetcher()
    scanner = MarketScanner()
    tracker = PortfolioTracker()
    val_engine = ValuationEngine()
    
    logger.info(">>> [V13.7] 启动玄铁量化 (Profit Display + Risk Alert)...")
    tracker.confirm_trades()
    try: analyst = NewsAnalyst()
    except: analyst = None

    macro_news = scanner.get_macro_news()
    macro_str = " | ".join([n['title'] for n in macro_news])
    results = []; cio_lines = [f"市场环境: {macro_str}"]
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_fund = {executor.submit(process_single_fund, fund, config, fetcher, scanner, tracker, val_engine, analyst, macro_str, config['global']['base_invest_amount'], config['global']['max_daily_invest']): fund for fund in config['funds']}
        for future in as_completed(future_to_fund):
            try:
                res, log = future.result()
                if res: results.append(res); cio_lines.append(log)
            except Exception as e: logger.error(f"线程异常: {e}")

    if results:
        results.sort(key=lambda x: -x['tech'].get('final_score', 0))
        cio = analyst.review_report("\n".join(cio_lines)) if analyst else ""
        adv = analyst.advisor_review("\n".join(cio_lines), macro_str) if analyst else ""
        html = render_html_report_v13(macro_news, results, cio, adv) 
        send_email("🗡️ 玄铁量化 V13.7 收益手谕", html)

if __name__ == "__main__": main()
