import yaml
import os
import time
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
from market_scanner import MarketScanner
from technical_analyzer import TechnicalAnalyzer
from valuation_engine import ValuationEngine # [V13 新增]
from portfolio_tracker import PortfolioTracker
from utils import send_email, logger

def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# [V13 核心逻辑]
def calculate_position_v13(tech, ai_adj, val_mult, val_desc, base_amt, max_daily, pos, strategy_type):
    """
    V13.0 决策矩阵：技术(Tactical) x 估值(Strategic)
    """
    # 1. 计算战术得分 (Tactical Score)
    # 范围: 0 - 100
    base_score = tech['quant_score']
    # CIO 修正 (AI Adjustment)
    tactical_score = max(0, min(100, base_score + ai_adj))
    
    tech['final_score'] = tactical_score
    tech['ai_adjustment'] = ai_adj
    
    # 2. 初始战术动作 (Tactical Action)
    # 系数范围: -1.0 (卖出) 到 2.0 (大力买入)
    tactical_mult = 0
    reasons = []

    # --- 战术层：看趋势和情绪 ---
    if tactical_score >= 85: tactical_mult = 2.0; reasons.append("战术:极强")
    elif tactical_score >= 70: tactical_mult = 1.0; reasons.append("战术:走强")
    elif tactical_score >= 60: tactical_mult = 0.5; reasons.append("战术:企稳")
    elif tactical_score <= 25: tactical_mult = -1.0; reasons.append("战术:破位")
    # 25-60分之间为观望 (multiplier=0)

    # 3. 战略修正 (Strategic Adjustment)
    # 用估值乘数去修正战术动作
    # val_mult 来源: 0.0(极贵) - 2.0(极便宜)
    
    final_mult = tactical_mult
    
    # [场景A] 战术看多 (要买)
    if tactical_mult > 0:
        # 如果估值极贵 (val_mult < 0.5)，强制刹车
        if val_mult < 0.5:
            final_mult = 0
            reasons.append(f"战略:高估刹车({val_desc})")
        # 如果估值便宜 (val_mult > 1.0)，放大买入
        elif val_mult > 1.0:
            final_mult *= val_mult # 例如 1.0 * 1.5 = 1.5倍买入
            reasons.append(f"战略:低估加倍({val_desc})")
            
    # [场景B] 战术看空 (要卖)
    elif tactical_mult < 0:
        # 如果估值极便宜 (val_mult > 1.2)，可能是在挖黄金坑，卖出要谨慎
        if val_mult > 1.2:
            final_mult = 0 # 忍住不卖，死扛
            reasons.append(f"战略:底部锁仓({val_desc})")
        # 如果估值也贵，那就坚决卖
        elif val_mult < 0.8:
            final_mult *= 1.5 # 加速清仓
            reasons.append("战略:高估止损")
            
    # [场景C] 战术观望 (Hold)
    else:
        # 如果极度低估 (val_mult >= 1.5)，即使技术面不好，也开启左侧定投
        if val_mult >= 1.5 and strategy_type in ['core', 'dividend']:
            final_mult = 0.5
            reasons.append(f"战略:左侧定投({val_desc})")

    # 4. 边界条件风控
    # 锁仓期检查
    held_days = pos.get('held_days', 999)
    if final_mult < 0 and pos['shares'] > 0 and held_days < 7:
        final_mult = 0
        reasons.append(f"风控:锁仓({held_days}天)")

    # 5. 计算最终金额
    final_amt = 0
    is_sell = False
    sell_val = 0
    label = "观望"

    # 限制单日上限
    if final_mult > 0:
        # 基础金额 * 最终系数
        amt = int(base_amt * final_mult)
        final_amt = max(0, min(amt, int(max_daily)))
        label = "买入"
    elif final_mult < 0:
        is_sell = True
        # 卖出比例
        sell_ratio = min(abs(final_mult), 1.0)
        sell_val = pos['shares'] * tech['price'] * sell_ratio
        label = "卖出"

    if reasons:
        tech['quant_reasons'] = reasons
        # 保存估值信息供UI展示
        tech['valuation_desc'] = val_desc

    return final_amt, label, is_sell, sell_val

def render_html_report(macro_list, results, daily_cap, cio, advisor):
    # (此处代码与 V12.3 保持一致，但需要微调以显示估值信息，下文会给出)
    # 为了节省篇幅，这里复用 V12.3 的 render_html_report 逻辑
    # 唯一需要修改的是在 HTML 生成部分加入 valuation_desc 的展示
    # ... (见下文完整渲染代码)
    pass

# [为了完整性，这里提供适配 V13 的 render 函数]
def render_html_report_v13(macro_list, results, cio, advisor):
    macro_html = "".join([f"<div style='font-size:12px;color:#eee;margin-bottom:6px;border-bottom:1px dashed #5d4037;padding-bottom:4px;'><span style='color:#ffb74d;'>●</span> {n['title']} <span style='color:#bbb;float:right;font-size:10px;'>[{n['source']}]</span></div>" for n in macro_list])
    
    rows = ""
    for r in results:
        # 颜色与样式
        color = "#d32f2f" if r['amount']>0 else ("#388e3c" if r.get('is_sell') else "#555")
        act = f"<span style='color:#ff8a80'>+{r['amount']}</span>" if r['amount']>0 else (f"<span style='color:#a5d6a7'>-{int(r.get('sell_value',0))}</span>" if r.get('is_sell') else "HOLD")
        
        # 理由标签
        reasons = " ".join([f"<span style='border:1px solid #666;padding:1px 3px;font-size:9px;border-radius:2px;color:#bbb;margin-right:3px;'>{x}</span>" for x in r['tech'].get('quant_reasons', [])])
        
        # 估值显示
        val_desc = r['tech'].get('valuation_desc', 'N/A')
        val_style = "color:#a5d6a7" if "低估" in val_desc else ("color:#ef5350" if "高估" in val_desc else "color:#999")

        # AI 文本
        ai_txt = ""
        if r.get('ai_analysis', {}).get('comment'):
            ai_txt = f"<div style='font-size:12px;color:#d7ccc8;margin-top:8px;padding:8px;background:rgba(0,0,0,0.3);border-left:2px solid #ffb74d;'><strong>✦</strong> {r['ai_analysis']['comment']}</div>"

        rows += f"""
        <div style="background:linear-gradient(90deg, #1b1b1b 0%, #000 100%);border-left:4px solid {color};margin-bottom:15px;padding:15px;border-radius:4px;box-shadow:0 4px 8px rgba(0,0,0,0.5);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div><span style="font-size:18px;font-weight:bold;color:#f0e6d2;">{r['name']}</span></div>
                <div style="color:#ffb74d;font-weight:bold;font-size:16px;">{r['tech'].get('final_score')} <span style="font-size:10px;color:#666;">SCORE</span></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin:8px 0;border-bottom:1px solid #333;padding-bottom:5px;">
                <span style="color:#ffb74d;font-weight:bold;">{r['position_type']}</span>
                <span>{act}</span>
            </div>
            <div style="font-size:11px;color:#bbb;margin-bottom:5px;">
                <span style="{val_style}">[估值] {val_desc}</span>
            </div>
            <div style="font-size:11px;color:#888;margin-bottom:8px;">{reasons}</div>
            {ai_txt}
        </div>"""

    return f"""<!DOCTYPE html><html><body style="background:#0a0a0a;color:#f0e6d2;font-family:sans-serif;max-width:660px;margin:0 auto;padding:20px;">
    <div style="border:2px solid #3e2723;border-top:5px solid #ffb74d;padding:20px;background:#111;">
        <h1 style="color:#ffb74d;text-align:center;font-size:24px;margin-bottom:5px;">XUANTIE QUANT V13</h1>
        <div style="text-align:center;font-size:10px;color:#8d6e63;letter-spacing:2px;margin-bottom:20px;">TACTICAL & STRATEGIC FUSION</div>
        <div style="background:#222;padding:10px;border:1px solid #3e2723;margin-bottom:20px;">{macro_html}</div>
        <div style="background:#151515;padding:15px;border:1px solid #3e2723;margin-bottom:20px;">{cio}</div>
        <div style="background:#1a1a1a;border-left:4px solid #5d4037;padding:15px;margin-bottom:20px;">{advisor}</div>
        {rows}
    </div></body></html>"""

def main():
    config = load_config()
    fetcher = DataFetcher()
    scanner = MarketScanner()
    tracker = PortfolioTracker()
    val_engine = ValuationEngine() # [V13] 实例化估值引擎
    
    logger.info(">>> [V13.0] 启动玄铁量化 (Cycle Anchor Edition)...")
    tracker.confirm_trades()
    try: analyst = NewsAnalyst()
    except: analyst = None

    macro_news = scanner.get_macro_news()
    macro_str = " | ".join([n['title'] for n in macro_news])
    results = []
    cio_lines = [f"市场环境: {macro_str}"]
    
    for fund in config['funds']:
        try:
            logger.info(f"Analyzing {fund['name']}...")
            # 1. 获取行情 & 技术分析
            data = fetcher.get_fund_history(fund['code'])
            if not data: continue
            tech = TechnicalAnalyzer.calculate_indicators(data)
            if not tech: continue
            
            pos = tracker.get_position(fund['code'])
            
            # 2. [V13] 获取估值状态 (战略层)
            val_mult, val_desc = val_engine.get_valuation_status(
                fund.get('index_name'), 
                fund.get('strategy_type')
            )
            logger.info(f"-> 估值状态: {val_desc} (系数: {val_mult})")

            # 3. AI 舆情分析 (战术层)
            ai_adj = 0
            ai_res = {}
            if analyst:
                # 只有在持仓或触发阈值时才调用AI，省钱
                if pos['shares']>0 or tech['quant_score']>=60 or tech['quant_score']<=35:
                    news = analyst.fetch_news_titles(fund['sector_keyword'])
                    ai_res = analyst.analyze_fund_v4(fund['name'], tech, macro_str, news)
                    ai_adj = ai_res.get('adjustment', 0)

            # 4. [V13] 综合决策
            amt, lbl, is_sell, s_val = calculate_position_v13(
                tech, ai_adj, 
                val_mult, val_desc, # 传入估值参数
                config['global']['base_invest_amount'], 
                config['global']['max_daily_invest'], 
                pos, fund.get('strategy_type')
            )
            
            # 5. 执行与记录
            tracker.record_signal(fund['code'], lbl)
            if amt>0: tracker.add_trade(fund['code'], fund['name'], amt, tech['price'])
            elif is_sell: tracker.add_trade(fund['code'], fund['name'], s_val, tech['price'], True)
            
            cio_lines.append(f"- {fund['name']}: {lbl} (Q:{tech['quant_score']} -> Final:{tech['final_score']} | {val_desc})")
            results.append({
                "name":fund['name'],"code":fund['code'],"amount":amt,"sell_value":s_val,
                "position_type":lbl,"is_sell":is_sell,"tech":tech,"ai_analysis":ai_res,
                "history":tracker.get_signal_history(fund['code'])
            })
            time.sleep(1) # 增加间隔，防止 akshare 访问过快
            
        except Exception as e: 
            logger.error(f"Err {fund['name']}: {e}")

    if results:
        results.sort(key=lambda x: -x['tech'].get('final_score', 0))
        cio = analyst.review_report("\n".join(cio_lines)) if analyst else ""
        adv = analyst.advisor_review("\n".join(cio_lines), macro_str) if analyst else ""
        # 使用新版渲染
        html = render_html_report_v13(macro_news, results, cio, adv)
        send_email("🗡️ 玄铁量化 V13.0 周期手谕", html)

if __name__ == "__main__": main()
