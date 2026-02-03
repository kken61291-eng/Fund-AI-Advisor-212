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
    💰 V6.4 Final: 终极仓位算法
    """
    score = tech_data['quant_score']
    weekly = tech_data['trend_weekly']
    price = tech_data['price']
    
    # 账本数据
    cost = pos_info['cost']
    shares = pos_info['shares']
    
    profit_pct = 0
    has_position = shares > 0
    if has_position:
        profit_pct = (price - cost) / cost * 100
        
    # 1. 基础倍数
    multiplier = 0
    if score >= 85: multiplier = 2.0
    elif score >= 70: multiplier = 1.0
    elif score >= 60: multiplier = 0.5
    elif score <= 15: multiplier = -1.0
    
    reasons = []

    # 2. 持仓反馈
    if has_position:
        if profit_pct > 20 and score < 70:
            multiplier = 0
            reasons.append(f"🔒止盈保利(盈{profit_pct:.1f}%)")
        elif profit_pct < -10 and score >= 80:
            multiplier = 3.0
            max_daily *= 1.5
            reasons.append(f"📉深套摊薄(亏{profit_pct:.1f}%)")
        elif profit_pct < -15 and score < 40:
             multiplier = -0.5
             reasons.append(f"✂️止损避险(亏{profit_pct:.1f}%)")

    # 3. 熊市风控
    if weekly == "DOWN" and multiplier > 0:
        multiplier *= 0.6
        max_daily *= 0.5
    
    # 4. 金额计算
    final_amount = 0
    is_sell = False
    sell_value = 0
    label = "观望 WAIT"

    if multiplier > 0:
        raw_amount = int(base_amount * multiplier)
        final_amount = max(0, min(raw_amount, int(max_daily)))
        
        if multiplier >= 2.0: label = "🔥 重仓 STRONG BUY"
        elif multiplier >= 1.0: label = "✅ 建仓 BUY"
        else: label = "🧪 试探 ACCUMULATE"

    elif multiplier < 0:
        is_sell = True
        sell_ratio = min(abs(multiplier), 1.0)
        position_value = shares * price
        sell_value = position_value * sell_ratio
        
        if (position_value - sell_value) < 10: 
            sell_value = position_value
            sell_ratio = 1.0

        if sell_ratio >= 0.99: label = "🚫 清仓 LIQUIDATE"
        else: label = f"✂️ 减仓 REDUCE {int(sell_ratio*100)}%"

    if reasons: tech_data['quant_reasons'].extend(reasons)
        
    return final_amount, label, is_sell, sell_value

def render_html_report(market_ctx, funds_results, daily_total_cap):
    """
    ✨ 鎏金典藏版 UI (Black Gold Premium)
    """
    invested = sum(r['amount'] for r in funds_results if r['amount'] > 0)
    cash_display = f"¥{invested:,}"
    
    # 宏观颜色
    north_val = market_ctx.get('north_money', '0')
    macro_color = "#D4AF37" # 金色默认
    if "+" in str(north_val): macro_color = "#ff4d4f" # 红
    elif "-" in str(north_val): macro_color = "#52c41a" # 绿

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Inter:wght@300;400;600&display=swap');
            
            body {{
                background-color: #050505;
                color: #e0e0e0;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                margin: 0;
                padding: 40px 10px;
                line-height: 1.5;
            }}
            .container {{
                max-width: 700px;
                margin: 0 auto;
                background: #0f0f0f;
                border: 1px solid #222;
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 20px 50px rgba(0,0,0,0.8);
            }}
            
            /* --- Header --- */
            .header {{
                background: linear-gradient(180deg, #1a1a1a 0%, #0f0f0f 100%);
                padding: 40px 30px;
                text-align: center;
                border-bottom: 1px solid #333;
                position: relative;
            }}
            .title {{
                font-family: 'Playfair Display', serif;
                font-size: 32px;
                margin: 0;
                background: linear-gradient(45deg, #BF953F, #FCF6BA, #B38728, #FBF5B7);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            .subtitle {{
                color: #666;
                font-size: 12px;
                margin-top: 10px;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}
            
            /* --- Dashboard --- */
            .dashboard {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 1px;
                background: #222; /* Grid border color */
                border-bottom: 1px solid #222;
            }}
            .stat-box {{
                background: #0f0f0f;
                padding: 20px;
                text-align: center;
            }}
            .stat-label {{
                color: #555;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 5px;
            }}
            .stat-value {{
                font-size: 20px;
                font-weight: 600;
                color: #fff;
            }}
            
            /* --- List --- */
            .fund-list {{
                padding: 0;
            }}
            .fund-card {{
                padding: 25px 30px;
                border-bottom: 1px solid #1a1a1a;
                transition: background 0.3s;
                position: relative;
            }}
            .fund-card:hover {{
                background: #141414;
            }}
            
            /* High Score Glow Effect */
            .premium-card {{
                background: linear-gradient(90deg, rgba(212,175,55,0.05) 0%, rgba(0,0,0,0) 100%);
                border-left: 3px solid #D4AF37;
            }}

            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }}
            .fund-name {{
                font-size: 16px;
                font-weight: 600;
                color: #fff;
            }}
            .fund-code {{
                font-size: 12px;
                color: #444;
                margin-left: 8px;
                font-family: monospace;
            }}
            
            .score-badge {{
                font-family: 'Playfair Display', serif;
                font-size: 24px;
                font-weight: 700;
                color: #444;
            }}
            .score-high {{
                background: linear-gradient(45deg, #BF953F, #B38728);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            
            /* Action Button Style */
            .action-tag {{
                display: inline-block;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }}
            .act-buy {{ background: rgba(50, 205, 50, 0.1); color: #4ade80; border: 1px solid rgba(50, 205, 50, 0.2); }}
            .act-sell {{ background: rgba(220, 20, 60, 0.1); color: #f87171; border: 1px solid rgba(220, 20, 60, 0.2); }}
            .act-wait {{ background: rgba(255, 255, 255, 0.05); color: #666; }}
            
            .metrics {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 10px;
                margin-top: 15px;
                padding-top: 15px;
                border-top: 1px solid #1a1a1a;
                font-size: 12px;
                color: #888;
            }}
            .metric-item b {{ color: #ccc; }}
            
            .reasons {{
                margin-top: 12px;
                font-size: 12px;
                color: #D4AF37; /* Gold text */
                opacity: 0.8;
                font-style: italic;
            }}
            
            .footer {{
                padding: 30px;
                text-align: center;
                color: #333;
                font-size: 11px;
                border-top: 1px solid #222;
                background: #0a0a0a;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="title">Quant V6.4</h1>
                <div class="subtitle">Premium Algo-Trading Report</div>
            </div>
            
            <div class="dashboard">
                <div class="stat-box">
                    <div class="stat-label">Market Sentiment</div>
                    <div class="stat-value" style="color: {macro_color}">{market_ctx.get('north_label')} {market_ctx.get('north_money')}</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Daily Allocation</div>
                    <div class="stat-value" style="color: #D4AF37">{cash_display}</div>
                </div>
            </div>
            
            <div class="fund-list">
    """
    
    # 逻辑：先显示交易的，再显示观望的
    active_funds = [f for f in funds_results if f['amount'] > 0 or f.get('is_sell')]
    passive_funds = [f for f in funds_results if f['amount'] == 0 and not f.get('is_sell')]
    
    # 渲染卡片函数
    def render_card(r, is_active):
        score = r['tech']['quant_score']
        is_premium = score >= 80 or r['amount'] >= 500
        card_class = "fund-card premium-card" if is_premium else "fund-card"
        score_class = "score-badge score-high" if score >= 60 else "score-badge"
        
        # Action Tag
        if r['amount'] > 0:
            act_class = "act-buy"
            act_text = f"BUY ¥{r['amount']}"
        elif r.get('is_sell'):
            act_class = "act-sell"
            val = int(r.get('sell_amount', 0))
            act_text = f"SELL ¥{val}" if val > 0 else "LIQUIDATE"
        else:
            act_class = "act-wait"
            act_text = "WAIT"

        # Tech Data
        trend_icon = "▲" if r['tech']['trend_weekly'] == "UP" else "▼"
        trend_col = "#4ade80" if r['tech']['trend_weekly'] == "UP" else "#666"

        return f"""
        <div class="{card_class}">
            <div class="card-header">
                <div>
                    <span class="fund-name">{r['name']}</span>
                    <span class="fund-code">{r['code']}</span>
                </div>
                <div class="{score_class}">{score}</div>
            </div>
            
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div class="action-tag {act_class}">{act_text}</div>
                <div style="font-size:12px; color:#555;">{r['position_type']}</div>
            </div>
            
            <div class="metrics">
                <div class="metric-item">RSI: <b>{r['tech']['rsi']}</b></div>
                <div class="metric-item">Bias: <b>{r['tech']['bias_20']}%</b></div>
                <div class="metric-item">Trend: <b style="color:{trend_col}">{trend_icon} {r['tech']['trend_weekly']}</b></div>
            </div>
            
            <div class="reasons">
                {' • '.join(r['tech']['quant_reasons'][:3])}
            </div>
        </div>
        """

    # 1. 渲染活跃交易
    if active_funds:
        html += "<div style='padding:15px 30px; color:#D4AF37; font-size:12px; letter-spacing:1px; border-bottom:1px solid #222;'>// EXECUTIONS</div>"
        for r in active_funds:
            html += render_card(r, True)
            
    # 2. 渲染观望清单 (折叠)
    if passive_funds:
        html += """
        <details>
            <summary style="padding:20px 30px; cursor:pointer; color:#444; font-size:12px; letter-spacing:1px; outline:none;">
                // WATCHLIST ({count})
            </summary>
        """.format(count=len(passive_funds))
        
        for r in passive_funds:
            html += render_card(r, False)
        
        html += "</details>"

    html += """
            </div>
            <div class="footer">
                GENERATED BY QUANTUM ENGINE V6.4 | ABSOLUTE RETURN STRATEGY
            </div>
        </div>
    </body>
    </html>
    """
    return html

def main():
    config = load_config()
    fetcher = DataFetcher()
    scanner = MarketScanner()
    tracker = PortfolioTracker() 
    
    logger.info(">>> 正在确认 T+1 交易...")
    tracker.confirm_trades()
    
    try: analyst = NewsAnalyst()
    except: analyst = None

    logger.info(">>> 启动 V6.4 鎏金版...")
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
                "name": fund['name'],
                "code": fund['code'],
                "amount": final_amt,
                "sell_amount": sell_amt,
                "position_type": pos_type,
                "is_sell": is_sell,
                "tech": tech_indicators
            })

            time.sleep(0.5)

        except Exception as e:
            logger.error(f"分析失败: {e}")

    if funds_results:
        funds_results.sort(key=lambda x: x['tech']['quant_score'], reverse=True)
        html_report = render_html_report(market_ctx, funds_results, MAX_DAILY)
        send_email("📊 Quant V6.4 Daily Report", html_report)

if __name__ == "__main__":
    main()
