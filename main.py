import yaml
import os
import time
from datetime import datetime
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
from market_scanner import MarketScanner
from technical_analyzer import TechnicalAnalyzer
from utils import send_email, logger

def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def calculate_position(action, confidence, base_amount):
    """
    💰 核心搞钱算法：动态仓位管理
    只有在高胜率(高信心)时才下重注
    """
    if "卖" in action or "清仓" in action:
        return 0, "卖出/止盈"
    
    if "观望" in action:
        return 0, "观望"

    # 买入逻辑
    if "强力" in action or confidence >= 8:
        # 信心爆棚，2.5倍杠杆（相对于基础金额）
        return int(base_amount * 2.5), "🔥 重仓出击"
    elif "买" in action and confidence >= 6:
        # 正常买入
        return int(base_amount), "✅ 标准定投"
    else:
        # 信心不足（虽然AI说买，但分不高），不买
        return 0, "⚠️ 信心不足(暂缓)"

def render_html_report(market_ctx, funds_results):
    COLOR_RED = "#d32f2f"     # 涨/买
    COLOR_GREEN = "#2e7d32"   # 跌/卖
    COLOR_BG = "#f5f7fa"      # 极简灰背景
    
    # 宏观颜色
    north_val = market_ctx.get('north_money', 0)
    try: check_val = float(str(north_val).replace('%', ''))
    except: check_val = 0
    north_color = COLOR_RED if check_val > 0 else COLOR_GREEN
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: {COLOR_BG}; margin: 0; padding: 20px; color: #333; }}
            .container {{ max-width: 650px; margin: 0 auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); overflow: hidden; }}
            .header {{ background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%); color: #333; padding: 25px; text-align: center; }}
            .market-box {{ display: flex; padding: 15px; border-bottom: 1px solid #eee; gap: 10px; }}
            .card {{ padding: 20px; border-bottom: 1px solid #eee; transition: all 0.2s; }}
            .card:hover {{ background-color: #fafafa; }}
            .tag {{ padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
            .buy-tag {{ background: #ffebee; color: {COLOR_RED}; }}
            .sell-tag {{ background: #e8f5e9; color: {COLOR_GREEN}; }}
            .wait-tag {{ background: #f5f5f5; color: #999; }}
            .glossary {{ background: #f8f9fa; padding: 20px; font-size: 13px; color: #666; border-top: 1px solid #eee; }}
            .glossary h4 {{ margin: 0 0 10px 0; color: #333; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin:0; font-size:22px;">💰 AI 绝对收益内参 (V5.0)</h1>
                <p style="margin:5px 0 0; font-size:13px; opacity:0.8;">{datetime.now().strftime('%Y-%m-%d')} | 目标：多挣钱，少回撤</p>
            </div>
            
            <div class="market-box">
                <div style="flex:1; background:#fff; border:1px solid #eee; border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:12px; color:#999;">北向资金</div>
                    <div style="font-size:18px; font-weight:bold; color:{north_color};">{north_val}</div>
                </div>
                <div style="flex:2; background:#fff; border:1px solid #eee; border-radius:8px; padding:10px;">
                    <div style="font-size:12px; color:#999;">🔥 领涨风口</div>
                    <div style="font-size:13px; color:#333; margin-top:3px;">
                        {' '.join(market_ctx.get('top_sectors', ['暂无'])[:3])}
                    </div>
                </div>
            </div>
    """

    all_glossary = {} # 收集所有名词解释

    for res in funds_results:
        # 收集名词
        if 'glossary' in res['ai'] and res['ai']['glossary']:
            all_glossary.update(res['ai']['glossary'])

        action = res['action']
        amt_display = f"¥{res['amount']}" if res['amount'] > 0 else "0"
        
        # 标签颜色逻辑
        if res['amount'] > 0:
            tag_class = "buy-tag"
            act_text = f"{res['position_type']} {amt_display}" # 例如：🔥 重仓出击 ¥500
        elif "卖" in action:
            tag_class = "sell-tag"
            act_text = "🚫 建议卖出"
        else:
            tag_class = "wait-tag"
            act_text = "☕️ 观望等待"

        # 周线提示
        weekly_trend = res['tech'].get('trend_weekly', 'UNKNOWN')
        trend_icon = "📈" if weekly_trend == "UP" else "📉"
        trend_color = COLOR_RED if weekly_trend == "UP" else COLOR_GREEN

        html += f"""
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <div>
                        <strong style="font-size:16px;">{res['name']}</strong>
                        <span style="font-size:12px; color:#999; margin-left:5px;">{res['code']}</span>
                    </div>
                    <div class="tag {tag_class}">{act_text}</div>
                </div>
                
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; font-size:13px; color:#666; margin-bottom:12px;">
                    <div>RSI: <b style="color:#333">{res['tech']['rsi']}</b></div>
                    <div>大势: <span style="color:{trend_color}">{trend_icon} {weekly_trend}</span></div>
                    <div>AI信心: <b style="color:#FF9800">{res['ai'].get('confidence', 0)}/10</b></div>
                    <div>乖离: {res['tech']['bias_20']}%</div>
                </div>

                <div style="background:#fff8e1; padding:10px; border-radius:6px; font-size:14px; color:#5d4037; line-height:1.5;">
                    <b>💡 操盘逻辑:</b> {res['ai']['thesis']}
                </div>
                
                <div style="margin-top:8px; font-size:12px;">
                    <span style="color:{COLOR_RED}">[利多]</span> {res['ai'].get('pros', '-')} <br>
                    <span style="color:{COLOR_GREEN}">[风险]</span> {res['ai'].get('risk_warning', '-')}
                </div>
            </div>
        """
    
    # 底部名词解释区域
    if all_glossary:
        html += '<div class="glossary"><h4>📖 操盘手人话词典 (AI生成)</h4>'
        for term, explain in all_glossary.items():
            html += f'<p><b>【{term}】</b>: {explain}</p>'
        html += '</div>'

    html += "</div></body></html>"
    return html

def main():
    config = load_config()
    fetcher = DataFetcher()
    scanner = MarketScanner()
    # 强制初始化
    try: analyst = NewsAnalyst()
    except: analyst = None

    logger.info(">>> 启动 V5.0 绝对收益引擎...")
    market_ctx = scanner.get_market_sentiment()
    funds_results = []
    
    # 基础金额 (200元)
    BASE_AMT = config['global']['base_invest_amount']

    for fund in config['funds']:
        try:
            logger.info(f"=== 深度分析 {fund['name']} ===")
            
            # 1. 极速获取数据
            data_dict = fetcher.get_fund_history(fund['code'])
            
            # 2. Python 硬算指标
            tech_indicators = TechnicalAnalyzer.calculate_indicators(data_dict)
            
            if not tech_indicators:
                logger.warning("数据不足，跳过")
                continue

            # 3. AI 操盘手思考
            ai_result = {
                "thesis": "AI 离线", "action_advice": "观望", 
                "confidence": 0, "pros": "", "cons": "", "glossary": {}
            }
            if analyst:
                news = analyst.fetch_news_titles(fund['sector_keyword'])
                ai_result = analyst.analyze_fund_v4(fund['name'], tech_indicators, market_ctx, news)

            # 4. 搞钱算法：计算仓位
            final_amt, pos_type = calculate_position(
                ai_result.get('action_advice', '观望'),
                ai_result.get('confidence', 0),
                BASE_AMT
            )
            
            funds_results.append({
                "name": fund['name'],
                "code": fund['code'],
                "action": ai_result.get('action_advice', '观望'),
                "amount": final_amt,
                "position_type": pos_type, # 如：重仓出击 / 标准定投
                "tech": tech_indicators,
                "ai": ai_result
            })

            logger.info(f"决策: {pos_type} | 金额: {final_amt} | 信心: {ai_result.get('confidence')}")
            time.sleep(1) # 极速版仅需1秒冷却

        except Exception as e:
            logger.error(f"分析失败: {e}")

    if funds_results:
        html_report = render_html_report(market_ctx, funds_results)
        send_email("💰 AI 绝对收益内参 (V5.0)", html_report)

if __name__ == "__main__":
    main()
