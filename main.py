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

def calculate_position(tech_data, base_amount, max_daily, pos_info):
    """
    💰 V7.1 核心算法: 散户生存优先
    """
    score = tech_data['quant_score']
    weekly = tech_data['trend_weekly']
    price = tech_data['price']
    
    cost = pos_info['cost']
    shares = pos_info['shares']
    held_days = pos_info.get('held_days', 999) # 默认为久持
    
    profit_pct = 0
    has_position = shares > 0
    if has_position:
        profit_pct = (price - cost) / cost * 100
        
    # --- 1. 基础信号 ---
    multiplier = 0
    if score >= 85: multiplier = 2.0      # 极度超卖，重仓
    elif score >= 70: multiplier = 1.0    # 标准买点
    elif score >= 60: multiplier = 0.5    # 试探性
    elif score <= 15: multiplier = -1.0   # 卖出信号
    
    reasons = []

    # --- 2. 持仓风控 ---
    if has_position:
        if profit_pct > 15 and score < 60: 
            multiplier = 0
            reasons.append(f"🔒止盈保利(盈{profit_pct:.1f}%)")
        elif profit_pct < -10 and score >= 80:
            multiplier = 3.0
            max_daily *= 2.0
            reasons.append(f"📉深套摊薄(亏{profit_pct:.1f}%)")

    # --- 3. 🛡️ 七日锁 (核心防割肉) ---
    if multiplier < 0 and has_position and held_days < 7:
        multiplier = 0 
        reasons.append(f"🛡️七日锁(仅持{held_days}天)-拒付1.5%赎回费")
        logger.warning(f"触发七日锁: 强制取消卖出")

    # --- 4. 熊市防御 ---
    if weekly == "DOWN":
        if multiplier > 0: multiplier *= 0.5 
        if multiplier < 0 and has_position and held_days >= 7: multiplier = -1.0 

    # --- 5. 执行计算 ---
    final_amount = 0
    is_sell = False
    sell_value = 0
    # 默认中文标签
    label = "⏸️ 持币观望"

    if multiplier > 0:
        raw_amount = int(base_amount * multiplier)
        final_amount = max(0, min(raw_amount, int(max_daily)))
        if multiplier >= 2.0: label = "🔥 强力增持 (重仓)"
        elif multiplier >= 1.0: label = "✅ 标准建仓"
        else: label = "🧪 试探性买入"

    elif multiplier < 0:
        is_sell = True
        sell_ratio = min(abs(multiplier), 1.0)
        position_value = shares * price
        sell_value = position_value * sell_ratio
        
        if (position_value - sell_value) < 50: 
            sell_value = position_value
            sell_ratio = 1.0

        if sell_ratio >= 0.99: label = "🚫 清仓离场 (落袋)"
        else: label = f"✂️ 减仓锁定 ({int(sell_ratio*100)}%)"

    if reasons: tech_data['quant_reasons'].extend(reasons)
        
    return final_amount, label, is_sell, sell_value

def render_html_report(market_ctx, funds_results, daily_total_cap):
    """
    ✨ V7.1 鎏金财富版 UI (Black Gold)
    """
    invested = sum(r['amount'] for r in funds_results if r['amount'] > 0)
    cash_display = f"{invested:,}"
    
    buys = [r for r in funds_results if r['amount'] > 0]
    sells = [r for r in funds_results if r.get('is_sell')]
    waits = [r for r in funds_results if r['amount'] == 0 and not r.get('is_sell')]

    north_val = market_ctx.get('north_money', '0')
    macro_class = "macro-neu"
    if "+" in str(north_val) and "0.00" not in str(north_val): macro_class = "macro-up"
    elif "-" in str(north_val): macro_class = "macro-down"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;700&family=Roboto+Mono&display=swap');
            body {{
                background-color: #0a0a0a; color: #e0e0e0;
                font-family: "Noto Serif SC", serif; margin: 0; padding: 20px;
                background-image: url('https://www.transparenttextures.com/patterns/cubes.png');
            }}
            .container {{
                max-width: 680px; margin: 0 auto; background: #141414;
                border: 2px solid #D4AF37; border-radius: 12px; overflow: hidden;
            }}
            .gold-text {{
                background: linear-gradient(to right, #D4AF37, #FCEabb, #D4AF37);
                -webkit-background-clip: text; color: transparent; font-weight: bold;
            }}
            .header {{
                background: linear-gradient(180deg, #1f1f1f 0%, #141414 100%);
                padding: 30px; text-align: center; border-bottom: 2px solid #D4AF37;
            }}
            .title {{ font-size: 28px; margin: 0; letter-spacing: 2px; }}
            .subtitle {{ color: #888; font-size: 12px; margin-top: 10px; }}
            .dashboard {{ display: flex; border-bottom: 1px solid #333; background: #1a1a1a; }}
            .dash-item {{ flex: 1; padding: 20px; text-align: center; border-right: 1px solid #333; }}
            .dash-item:last-child {{ border-right: none; }}
            .dash-title {{ font-size: 12px; color: #aaa; margin-bottom: 8px; }}
            .dash-value {{ font-size: 22px; font-family: "Roboto Mono", monospace; }}
            .macro-up {{ color: #ff4d4f; }} .macro-down {{ color: #52c41a; }} .macro-neu {{ color: #D4AF37; }}
            .section-title {{
                padding: 20px 30px 10px; color: #D4AF37; font-size: 16px; border-bottom: 1px solid #222;
            }}
            .card {{ margin: 15px 30px; background: #1c1c1c; border: 1px solid #333; border-radius: 8px; overflow: hidden; }}
            .card-buy {{ border-left: 4px solid #ff4d4f; }}
            .buy-header {{ background: rgba(255, 77, 79, 0.1); color: #ff4d4f; }}
            .card-sell {{ border-left: 4px solid #52c41a; }}
            .sell-header {{ background: rgba(82, 196, 26, 0.1); color: #52c41a; }}
            .card-top {{ padding: 12px 20px; display: flex; justify-content: space-between; font-family: "Roboto Mono"; font-weight: bold; }}
            .card-body {{ padding: 15px 20px; }}
            .fund-title {{ font-size: 16px; font-weight: bold; color: #fff; }}
            .fund-code {{ font-size: 12px; color: #666; margin-left: 5px; }}
            .score-box {{ float: right; font-family: "Roboto Mono"; color: #D4AF37; }}
            .reason-tag {{ display: inline-block; background: #252525; color: #aaa; padding: 4px 8px; border-radius: 4px; font-size: 11px; margin-right: 5px; margin-top: 8px; border: 1px solid #333; }}
            .reason-risk {{ color: #FCEabb; border-color: #D4AF37; background: rgba(212,175,55,0.1); }}
            summary {{ padding: 20px 30px; cursor: pointer; color: #666; font-size: 13px; }}
            .wait-list {{ padding: 0 30px 20px; font-size: 12px; color: #555; line-height: 1.8; }}
            .footer {{ padding: 25px; text-align: center; color: #444; font-size: 11px; background: #0f0f0f; border-top: 1px solid #222; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="title"><span class="gold-text">💰 鎏金量化·财富内参</span></h1>
                <div class="subtitle">{datetime.now().strftime('%Y年%m月%d日')} | V7.1 实战风控版</div>
            </div>
            <div class="dashboard">
                <div class="dash-item">
                    <div class="dash-title">🌍 市场风向标</div>
                    <div class="dash-value {macro_class}">{market_ctx.get('north_label')} {market_ctx.get('north_money')}</div>
                </div>
                <div class="dash-item">
                    <div class="dash-title">💸 今日投入金 (CNY)</div>
                    <div class="dash-value gold-text">¥{cash_display}</div>
                </div>
            </div>
    """

    if buys:
        html += '<div class="section-title">📈 财富增值机遇 (买入)</div>'
        for r in buys:
            html += f"""
            <div class="card card-buy">
                <div class="card-top buy-header">
                    <span>{r['position_type']}</span><span>+¥{r['amount']:,}</span>
                </div>
                <div class="card-body">
                    <div>
                        <span class="fund-title">{r['name']}</span><span class="fund-code">{r['code']}</span>
                        <span class="score-box">量化评分: {r['tech']['quant_score']}</span>
                    </div>
                    <div style="margin-top:10px;">{''.join([f'<span class="reason-tag {"reason-risk" if "风控" in x or "锁" in x else ""}">{x}</span>' for x in r['tech']['quant_reasons']])}</div>
                </div>
            </div>
            """

    if sells:
        html += '<div class="section-title">🛡️ 风险控制行动 (卖出)</div>'
        for r in sells:
            val = int(r.get('sell_value', 0))
            val_display = f"¥{val:,}" if val > 0 else "全部份额"
            html += f"""
            <div class="card card-sell">
                <div class="card-top sell-header">
                    <span>{r['position_type']}</span><span>卖出: {val_display}</span>
                </div>
                <div class="card-body">
                    <div>
                        <span class="fund-title">{r['name']}</span><span class="fund-code">{r['code']}</span>
                        <span class="score-box">量化评分: {r['tech']['quant_score']}</span>
                    </div>
                    <div style="margin-top:10px;">{''.join([f'<span class="reason-tag {"reason-risk" if "风控" in x or "锁" in x else ""}">{x}</span>' for x in r['tech']['quant_reasons']])}</div>
                </div>
            </div>
            """

    if waits:
        html += f"""
        <details>
            <summary>⏸️ 查看 {len(waits)} 只观望标的 (未触发信号)</summary>
            <div class="wait-list">{' • '.join([f"{r['name']}({r['tech']['quant_score']}分)" for r in waits])}</div>
        </details>
        """
    else: html += '<div style="padding:30px; text-align:center; color:#666;">今日全线出击，无观望标的。</div>'

    html += """
            <div class="footer">
                注：持有不足7天触发「七日锁」强制保护；高波动期自动打折。<br>SYSTEM GENERATED | 纪律执行是财富积累的前提
            </div>
        </div>
    </body></html>
    """
    return html

def main():
    config = load_config()
    fetcher = DataFetcher()
    scanner = MarketScanner()
    tracker = PortfolioTracker() 
    
    logger.info(">>> [V7.1] 启动 T+1 确认...")
    tracker.confirm_trades()
    
    try: analyst = NewsAnalyst()
    except: analyst = None

    logger.info(">>> 启动 V7.1 鎏金实战版...")
    market_ctx = scanner.get_market_sentiment()
    funds_results = []
    
    BASE_AMT = config['global']['base_invest_amount']
    MAX_DAILY = config['global']['max_daily_invest']

    for fund in config['funds']:
        try:
            logger.info(f"=== 分析 {fund['name']} ===")
            data_dict = fetcher.get_fund_history(fund['code'])
            tech_indicators = TechnicalAnalyzer.calculate_indicators(data_dict)
            if not tech_indicators: continue

            pos_info = tracker.get_position(fund['code'])
            final_amt, pos_type, is_sell, sell_amt = calculate_position(tech_indicators, BASE_AMT, MAX_DAILY, pos_info)
            
            if final_amt > 0:
                tracker.add_trade(fund['code'], fund['name'], final_amt, tech_indicators['price'], is_sell=False)
            elif is_sell and sell_amt > 0:
                tracker.add_trade(fund['code'], fund['name'], sell_amt, tech_indicators['price'], is_sell=True)

            funds_results.append({
                "name": fund['name'], "code": fund['code'],
                "amount": final_amt, "sell_value": sell_amt,
                "position_type": pos_type, "is_sell": is_sell,
                "tech": tech_indicators
            })
            time.sleep(0.5)

        except Exception as e: logger.error(f"分析失败: {e}")

    if funds_results:
        funds_results.sort(key=lambda x: x['tech']['quant_score'], reverse=True)
        html_report = render_html_report(market_ctx, funds_results, MAX_DAILY)
        send_email("📊 鎏金量化·财富内参", html_report)

if __name__ == "__main__":
    main()
