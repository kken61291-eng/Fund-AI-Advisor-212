import os
import re
import base64

# 配色方案常量
COLOR_GOLD = "#fab005" 
COLOR_RED = "#fa5252"  
COLOR_GREEN = "#51cf66" 
COLOR_TEXT_MAIN = "#e9ecef"
COLOR_TEXT_SUB = "#adb5bd"
COLOR_BG_MAIN = "#0f1215" 
COLOR_BG_CARD = "#16191d" 

def clean_markdown(text):
    """清洗 AI 回复中可能夹带的 Markdown 标记"""
    if not text: return ""
    text = re.sub(r'```(?:html|json|markdown)?', '', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'#+\s+', '', text)
    return text.strip()

def render_html_report_v17(all_news, results, cio_html, advisor_html):
    """
    [V17.0 UI 引擎] 生成全量化仪表盘 HTML
    """
    # 1. 处理顶部 CIO 和 顾问 Markdown
    cio_html = clean_markdown(cio_html)
    advisor_html = clean_markdown(advisor_html)
    
    # 2. 生成新闻列表 HTML
    news_html = "".join([f'<div style="font-size:11px;color:{COLOR_TEXT_SUB};margin-bottom:5px;border-bottom:1px solid #25282c;padding-bottom:3px;"><span style="color:{COLOR_GOLD};margin-right:4px;">●</span>{n}</div>' for n in all_news])
    
    # 3. 生成卡片列表
    rows = ""
    for r in results:
        tech = r.get('tech', {})
        ai_data = r.get('ai_analysis', {})
        
        # --- A. AI 观点提取 ---
        bull_say = clean_markdown(ai_data.get('cgo_proposal', {}).get('catalyst', '无明显催化'))
        bear_say = clean_markdown(ai_data.get('cro_audit', {}).get('max_drawdown_scenario', '无'))
        chairman = clean_markdown(ai_data.get('chairman_conclusion', '无结论'))

        # --- B. 交易动作样式 ---
        if r['amount'] > 0:
            act_style = f"background:rgba(250,82,82,0.15);color:{COLOR_RED};border:1px solid {COLOR_RED};"
            act_text = f"⚡ 买入 {r['amount']:,}"
        elif r['is_sell']:
            act_style = f"background:rgba(81,207,102,0.15);color:{COLOR_GREEN};border:1px solid {COLOR_GREEN};"
            act_text = f"💰 卖出 {int(r['sell_value']):,}"
        else:
            act_style = "background:rgba(255,255,255,0.05);color:#adb5bd;border:1px solid #495057;"
            act_text = "☕ 观望"

        # 量化理由标签
        reasons = " ".join([f"<span style='border:1px solid #444;background:rgba(255,255,255,0.05);padding:1px 4px;font-size:9px;border-radius:3px;color:{COLOR_TEXT_SUB};margin-right:3px;'>{x}</span>" for x in tech.get('quant_reasons', [])])

        # --- C. 全量量化指标提取 ---
        # 趋势与动量
        adx_val = tech.get('trend_strength', {}).get('adx', 0)
        trend_type = tech.get('trend_strength', {}).get('trend_type', '-')
        ma_align = tech.get('ma_alignment', '-')
        rsi_val = tech.get('rsi', '-')
        
        # 风险与波动
        atr_pct = tech.get('volatility', {}).get('atr_percent', 0)
        boll_pos = tech.get('bollinger', {}).get('pct_b', 0)
        
        # 资金与量能
        vol_ratio = tech.get('volume_analysis', {}).get('vol_ratio', 1.0)
        vr_24 = tech.get('volume_analysis', {}).get('vr_24', 100)
        macd_hist = tech.get('macd', {}).get('hist', 0)
        
        # 动态配色
        trend_color = COLOR_RED if trend_type == 'BULL' else (COLOR_GREEN if trend_type == 'BEAR' else COLOR_TEXT_SUB)
        hist_color = COLOR_RED if macd_hist > 0 else COLOR_GREEN

        rows += f"""<div class="card" style="border-left:3px solid {COLOR_GOLD}; background:{COLOR_BG_CARD}; margin-bottom:15px; padding:15px; border-radius:4px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:10px;align-items:center;">
                <span style="font-size:16px;font-weight:bold;color:{COLOR_TEXT_MAIN};">{r['name']} <span style="font-size:10px;color:#666;font-weight:normal;">({r['code']})</span></span>
                <span style="display:inline-block;padding:3px 10px;font-size:12px;font-weight:bold;border-radius:4px;{act_style}">{act_text}</span>
            </div>
            
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;align-items:flex-end;">
                 <div>
                    <span style="color:{COLOR_GOLD};font-weight:bold;font-size:18px;">{tech.get('final_score', 0)}分</span>
                    <span style="font-size:10px;color:{COLOR_TEXT_SUB};margin-left:5px;">(基准:{tech.get('quant_score',0)} + AI:{tech.get('ai_adjustment',0)})</span>
                 </div>
                 <div style="font-size:11px;color:{COLOR_TEXT_SUB};">风控: <span style="color:{COLOR_RED}">{tech.get('tech_cro_comment','-')}</span></div>
            </div>

            <div style="background:rgba(255,255,255,0.03); padding:8px; border-radius:4px; margin-bottom:10px;">
                <div class="tech-grid" style="display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 6px; font-size: 10px; color: {COLOR_TEXT_SUB};">
                    <span>RSI: <b style="color:{COLOR_TEXT_MAIN}">{rsi_val}</b></span>
                    <span>ADX: <b style="color:{trend_color}">{adx_val}</b></span>
                    <span>MA: <b style="color:{trend_color}">{ma_align}</b></span>
                    <span>MACD: <b style="color:{hist_color}">{macd_hist}</b></span>
                    
                    <span>ATR%: {atr_pct}%</span>
                    <span>布林%: {boll_pos}</span>
                    <span>量比: {vol_ratio}</span>
                    <span>VR24: {vr_24}</span>
                </div>
            </div>

            <div style="margin-top:5px;font-size:10px;color:{COLOR_TEXT_SUB};">{reasons}</div>
            
            <div style="margin-top:12px;border-top:1px solid #333;padding-top:10px;">
                <div style="border-left:2px solid {COLOR_GREEN};background:rgba(81,207,102,0.05);padding:6px;margin-bottom:4px;font-size:11px;">
                    <b style="color:{COLOR_GREEN}">CGO:</b> <span style="color:#c0ebc9;">{bull_say}</span>
                </div>
                <div style="border-left:2px solid {COLOR_RED};background:rgba(250,82,82,0.05);padding:6px;margin-bottom:4px;font-size:11px;">
                    <b style="color:{COLOR_RED}">CRO:</b> <span style="color:#ffc9c9;">{bear_say}</span>
                </div>
                <div style="background:rgba(250,176,5,0.05);padding:8px;border-radius:4px;border:1px solid rgba(250,176,5,0.2);margin-top:6px;">
                    <div style="color:{COLOR_GOLD};font-size:11px;font-weight:bold;">⚖️ CIO 终审:</div>
                    <div style="color:{COLOR_TEXT_MAIN};font-size:11px;margin-top:2px;">{chairman}</div>
                </div>
            </div>
        </div>"""

    # 4. Logo & 页面封装
    logo_src = "[https://raw.githubusercontent.com/kken61291-eng/Fund-AI-Advisor/main/logo.png](https://raw.githubusercontent.com/kken61291-eng/Fund-AI-Advisor/main/logo.png)"
    if os.path.exists("logo.png"):
        try:
            with open("logo.png", "rb") as f:
                logo_src = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        except: pass

    return f"""<!DOCTYPE html><html><head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ background: {COLOR_BG_MAIN}; color: {COLOR_TEXT_MAIN}; font-family: 'Segoe UI', sans-serif; margin: 0; padding: 10px; }}
        .main-container {{ max-width: 600px; margin: 0 auto; background: #0a0c0e; border: 1px solid #2c3e50; padding: 10px; border-radius: 8px; }}
        .cio-content {{ line-height: 1.5; font-size: 12px; color: {COLOR_TEXT_MAIN}; }}
        @media (max-width: 480px) {{ .tech-grid {{ grid-template-columns: 1fr 1fr !important; }} }}
    </style></head><body>
    <div class="main-container">
        <div style="text-align:center; padding-bottom:15px; border-bottom:1px solid #222;">
            <img src="{logo_src}" style="width:160px; max-width:60%; display:block; margin:0 auto;">
            <div style="font-size:9px; color:{COLOR_GOLD}; letter-spacing:2px; margin-top:5px;">V17.0 FULL-QUANT ENGINE</div>
        </div>
        
        <div style="background:{COLOR_BG_CARD};margin-top:15px;padding:12px;border-radius:4px;margin-bottom:10px;">
            <div style="color:{COLOR_GOLD};font-weight:bold;font-size:12px;border-bottom:1px solid #333;padding-bottom:5px;margin-bottom:8px;">📡 市场宏观 & 舆情</div>
            {news_html}
        </div>
        
        <div style="background:{COLOR_BG_CARD};padding:12px;border-radius:4px;border-left:3px solid {COLOR_RED};margin-bottom:10px;">
            <div style="color:{COLOR_RED};font-weight:bold;font-size:12px;margin-bottom:5px;">🛑 CIO 战略审计</div>
            <div class="cio-content">{cio_html}</div>
        </div>
        
        <div style="background:{COLOR_BG_CARD};padding:12px;border-radius:4px;border-left:3px solid {COLOR_GOLD};margin-bottom:10px;">
            <div style="color:{COLOR_GOLD};font-weight:bold;font-size:12px;margin-bottom:5px;">🐦 趋势一致性审计</div>
            <div class="cio-content">{advisor_html}</div>
        </div>
        
        {rows}
        <div style="text-align:center; color:#444; font-size:9px; margin-top:20px;">POWERED BY DEEPSEEK & GEMINI</div>
    </div></body></html>"""
