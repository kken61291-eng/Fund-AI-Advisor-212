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
    
    # 从账本获取数据
    cost = pos_info['cost']
    shares = pos_info['shares']
    
    # 计算持仓盈亏 (现价-成本)/成本
    profit_pct = 0
    has_position = shares > 0
    if has_position:
        profit_pct = (price - cost) / cost * 100
        
    # --- 1. 基础倍数决策 ---
    multiplier = 0
    if score >= 85: multiplier = 2.0      # 极度超卖，重仓
    elif score >= 70: multiplier = 1.0    # 标准买点
    elif score >= 60: multiplier = 0.5    # 试探性
    elif score <= 15: multiplier = -1.0   # 触发卖出信号
    
    reasons = []

    # --- 2. 持仓反馈修正 ---
    if has_position:
        if profit_pct > 20 and score < 70:
            multiplier = 0
            reasons.append(f"🔒止盈保利(盈{profit_pct:.1f}%)")
        elif profit_pct < -10 and score >= 80:
            multiplier = 3.0
            max_daily *= 1.5
            reasons.append(f"📉深套摊薄(亏{profit_pct:.1f}%)")
        elif profit_pct < -15 and score < 40:
             multiplier = -0.5 # 触发减仓
             reasons.append(f"✂️止损避险(亏{profit_pct:.1f}%)")

    # --- 3. 熊市风控 ---
    if weekly == "DOWN" and multiplier > 0:
        multiplier *= 0.6
        max_daily *= 0.5
    
    # --- 4. 最终金额计算 ---
    final_amount = 0
    is_sell = False
    sell_value = 0 # 卖出市值
    label = "⏸️ 空仓观望"

    if multiplier > 0:
        # 买入逻辑
        raw_amount = int(base_amount * multiplier)
        final_amount = max(0, min(raw_amount, int(max_daily)))
        
        if multiplier >= 2.0: label = "🔥 重仓出击"
        elif multiplier >= 1.0: label = "✅ 标准建仓"
        else: label = "🧪 试探仓位"

    elif multiplier < 0:
        # 卖出逻辑 (优化版)
        is_sell = True
        sell_ratio = min(abs(multiplier), 1.0) # 最大100%
        
        # 计算持仓总市值
        position_value = shares * price
        
        # 计算计划卖出市值
        sell_value = position_value * sell_ratio
        
        # 修正精度误差，如果这就剩一点点了，索性全卖
        if (position_value - sell_value) < 10: 
            sell_value = position_value
            sell_ratio = 1.0

        if sell_ratio >= 0.99: label = "🚫 清仓止盈/止损"
        else: label = f"✂️ 减仓{int(sell_ratio*100)}%"

    if reasons: tech_data['quant_reasons'].extend(reasons)
        
    return final_amount, label, is_sell, sell_value

def render_html_report(market_ctx, funds_results, daily_total_cap):
    invested = sum(r['amount'] for r in funds_results if r['amount'] > 0)
    cash_display = f"¥{invested}"
    
    html = f"""
    <html><body style="font-family: -apple-system, sans-serif; background:#0f1419; color:#e6e6e6; padding:20px;">
    <div style="max-width:650px; margin:0 auto; background:#1a1f2e; padding:24px; border-radius:12px; border:1px solid #2d3748;">
        <div style="text-align:center; margin-bottom:24px;">
            <h2 style="margin:0; color:#4fd1c5; font-size:24px;">QUANT V6.4 (Gold Master)</h2>
            <div style="color:#8892b0; font-size:13px; margin-top:8px;">
                {datetime.now().strftime('%Y-%m-%d %H:%M')} | 今日操作: <span style="color:#{'48bb78' if invested>0 else '#8892b0'}">{cash_display}</span>
            </div>
            <div style="margin-top:12px; padding:12px; background:#0d1117; border-radius:6px; font-size:12px;">
                🌍 {market_ctx.get('north_label', '宏观')} ({market_ctx.get('north_money', '-')})
            </div>
        </div>
        
        <div style="margin-bottom:20px;">
        {''.join(f"""
        <div style="background:#0d1117; margin:8px 0; padding:16px; border-radius:8px; border-left:4px solid {'#48bb78' if r['amount']>0 else '#f56565' if r.get('is_sell') else '#4a5568'};">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-weight:bold; font-size:15px;">{r['name']}</div>
                    <div style="color:#8892b0; font-size:11px;">{r['code']} | 评分: <span style="color:#{'48bb78' if r['tech']['quant_score']>=60 else 'ed8936' if r['tech']['quant_score']>=40 else 'f56565'}">{r['tech']['quant_score']}</span></div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:18px; font-weight:bold; color:{'#48bb78' if r['amount']>0 else '#f56565' if r.get('is_sell') else '#8892b0'};">
                        {'+' if r['amount']>0 else '-'}¥{r['amount'] if r['amount']>0 else int(r.get('sell_amount',0)) if r.get('is_sell') else '0'}
                    </div>
                    <div style="font-size:11px; color:#8892b0;">{r['position_type']}</div>
                </div>
            </div>
            <div style="margin-top:10px; font-size:12px; color:#a0aec0; line-height:1.5;">
                {' • '.join(r['tech']['quant_reasons'][:3])}
            </div>
        </div>
        """ for r in funds_results if r['amount']>0 or r.get('is_sell'))}
        </div>
    </div></body></html>
    """
    return html

def main():
    config = load_config()
    fetcher = DataFetcher()
    scanner = MarketScanner()
    tracker = PortfolioTracker() 
    
    # 1. 每日第一件事：确认昨天的交易 (T+1)
    logger.info(">>> 正在确认 T+1 交易...")
    tracker.confirm_trades()
    
    try: analyst = NewsAnalyst()
    except: analyst = None

    logger.info(">>> 启动 V6.4 Gold Master...")
    market_ctx = scanner.get_market_sentiment()
    funds_results = []
    
    BASE_AMT = config['global']['base_invest_amount']
    MAX_DAILY = config['global']['max_daily_invest']

    for fund in config['funds']:
        try:
            logger.info(f"=== 分析 {fund['name']} ===")
            
            # 获取数据
            data_dict = fetcher.get_fund_history(fund['code'])
            tech_indicators = TechnicalAnalyzer.calculate_indicators(data_dict)
            if not tech_indicators: continue

            # 读取持仓 (包含已确认的)
            pos_info = tracker.get_position(fund['code'])
            
            # 计算决策 (终极版)
            final_amt, pos_type, is_sell, sell_amt = calculate_position(tech_indicators, BASE_AMT, MAX_DAILY, pos_info)
            
            # 记账 (加入 pending 队列)
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
        send_email("📊 V6.4 量化实战日报", html_report)

if __name__ == "__main__":
    main()
