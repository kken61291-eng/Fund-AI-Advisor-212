import os
import re
import base64

# --- V17.2 配色方案 (高对比度) ---
COLOR_GOLD = "#ffd700"       # 核心金 (更亮)
COLOR_RED = "#ff4d4f"        # 警示红
COLOR_GREEN = "#52c41a"      # 极客绿
COLOR_TEXT_MAIN = "#ffffff"  # 纯白 (主文本)
COLOR_TEXT_SUB = "#a6a6a6"   # 浅灰 (副文本)
COLOR_BG_PAGE = "#0a0a0a"    # 页面背景
COLOR_BG_CARD = "#141414"    # 卡片背景
COLOR_BORDER = "#333333"     # 边框线

def format_markdown_to_html(text):
    """
    [V17.2 核心修复] 将 Markdown/混合文本 转换为漂亮的 HTML
    解决"报告仍然是 Markdown 格式"的问题
    """
    if not text: return "<span style='color:#666'>暂无内容</span>"
    
    # 1. 保护性清洗：移除 CSS/JS 源码，但保留 HTML 结构
    text = re.sub(r'```(?:html|json|xml|css)?', '', text)
    text = re.sub(r'```', '', text)
    text = re.sub(r'<style.*?>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. Markdown 语法转换 (正则替换)
    
    # 标题 (### Title -> <h4>Title</h4>)
    text = re.sub(r'^###\s+(.*?)$', r'<h4 style="margin:15px 0 8px 0; color:#ffd700; border-bottom:1px solid #333; padding-bottom:4px;">\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.*?)$', r'<h3 style="margin:20px 0 10px 0; color:#fff;">\1</h3>', text, flags=re.MULTILINE)
    
    # 加粗 (**text** -> <b>text</b>)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b style="color:#fff;">\1</b>', text)
    
    # 列表 (- item -> <li>item</li>)
    # 简单处理：将行首的 "- " 替换为带点的 div
    text = re.sub(r'^\s*-\s+(.*?)$', r'<div style="margin-bottom:4px; padding-left:15px; position:relative;"><span style="position:absolute; left:0; color:#ffd700;">•</span>\1</div>', text, flags=re.MULTILINE)
    
    # 换行处理 (将 \n 转换为 <br>, 但避开 HTML 标签内部)
    # 简单策略：如果段落间有空行，视为分段
    text = text.replace('\n\n', '<br><br>').replace('\n', '<br>')
    
    # 3. 字体颜色强制修正 (防止 AI 生成黑色的字)
    # 如果 AI 返回了 <font color="black"> 或者 style="color:#000", 强制替换
    text = re.sub(r'color:\s*#000000', 'color: #ffffff', text)
    text = re.sub(r'color:\s*black', 'color: #ffffff', text)

    return text.strip()

def render_html_report_v17(all_news, results, cio_html, advisor_html):
    """
    [V17.2 UI 引擎] 垂直布局 + 高亮字体
    """
    # 1. 格式化 AI 报告内容
    cio_content = format_markdown_to_html(cio_html)
    advisor_content = format_markdown_to_html(advisor_html)
    
    # 2. 新闻列表
    news_items = ""
    for n in all_news[:12]: 
        news_items += f'<div class="news-item"><span class="bullet">›</span>{n}</div>'
    
    # 3. 生成 ETF 卡片流
    cards_html = ""
    for r in results:
        tech = r.get('tech', {})
        ai_data = r.get('ai_analysis', {})
        
        # 提取并清洗观点 (移除 Markdown 符号)
        bull_say = re.sub(r'\*\*|`', '', ai_data.get('cgo_proposal', {}).get('catalyst', '无明显催化'))
        bear_say = re.sub(r'\*\*|`', '', ai_data.get('cro_audit', {}).get('max_drawdown_scenario', '无'))
        chairman = re.sub(r'\*\*|`', '', ai_data.get('chairman_conclusion', '无结论'))

        # 交易动作徽章
        if r['amount'] > 0:
            act_badge = f'<div class="badge buy">⚡ 买入 ¥{r["amount"]:,}</div>'
            card_border_color = COLOR_RED 
        elif r['is_sell']:
            act_badge = f'<div class="badge sell">🔻 卖出 ¥{int(r["sell_value"]):,}</div>'
            card_border_color = COLOR_GREEN
        else:
            act_badge = f'<div class="badge hold">☕ 观望</div>'
            card_border_color = COLOR_BORDER

        # 指标提取
        idx_info = f"{r.get('index_name', 'N/A')}"
        tags = "".join([f'<span class="tag">{x}</span>' for x in tech.get('quant_reasons', [])])
        
        # 动态颜色类
        trend_cls = 'text-red' if 'BULL' in str(tech.get('trend_strength', {}).get('trend_type')) else 'text-green'
        
        cards_html += f"""
        <div class="card" style="border-left: 3px solid {card_border_color};">
            <div class="card-header">
                <div>
                    <span class="stock-name">{r['name']}</span>
                    <span class="stock-code">{r['code']}</span>
                    <span class="index-code">({idx_info})</span>
                </div>
                {act_badge}
            </div>
            
            <div class="card-body">
                <div class="score-row">
                    <div>
                        <span class="main-score">{tech.get('final_score', 0)}</span>
                        <span class="sub-text">分 (基准{tech.get('quant_score',0)} + AI{tech.get('ai_adjustment',0)})</span>
                    </div>
                    <div class="sub-text">风控: <span style="color:{COLOR_RED}">{tech.get('tech_cro_comment','-')}</span></div>
                </div>

                <div class="metrics-grid">
                    <div>RSI: <b class="text-white">{tech.get('rsi','-')}</b></div>
                    <div>ADX: <b class="{trend_cls}">{tech.get('trend_strength', {}).get('adx', 0)}</b></div>
                    <div>MA: <b class="{trend_cls}">{tech.get('ma_alignment', '-')}</b></div>
                    <div>MACD: <b>{tech.get('macd', {}).get('hist', 0)}</b></div>
                    <div>ATR%: {tech.get('volatility', {}).get('atr_percent', 0)}%</div>
                    <div>量比: {tech.get('volume_analysis', {}).get('vol_ratio', 1)}</div>
                </div>

                <div style="margin: 10px 0;">{tags}</div>
                
                <div class="ai-box">
                    <div class="ai-row"><span class="role-label cgo">CGO</span> {bull_say}</div>
                    <div class="ai-row"><span class="role-label cro">CRO</span> {bear_say}</div>
                    <div class="ai-row cio-row"><span class="role-label cio">CIO</span> {chairman}</div>
                </div>
            </div>
        </div>"""

    # 4. Logo
    logo_src = "https://raw.githubusercontent.com/kken61291-eng/Fund-AI-Advisor/main/logo.png"
    if os.path.exists("logo.png"):
        try:
            with open("logo.png", "rb") as f:
                logo_src = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        except: pass

    # 5. HTML 组装
    return f"""<!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            /* --- V17.2 样式修复 --- */
            body {{ background-color: {COLOR_BG_PAGE}; color: {COLOR_TEXT_MAIN}; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 20px; font-size: 14px; line-height: 1.5; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            a {{ color: {COLOR_GOLD}; }}
            
            /* 头部 */
            .header {{ text-align: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #333; }}
            .title {{ color: {COLOR_GOLD}; font-size: 12px; letter-spacing: 4px; margin-top: 8px; font-weight: bold; text-transform: uppercase; }}
            
            /* 垂直布局 (Vertical Layout) */
            .box {{ background: {COLOR_BG_CARD}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; overflow: hidden; margin-bottom: 20px; }}
            .box-header {{ background: #1f1f1f; padding: 12px 15px; font-size: 14px; font-weight: bold; border-bottom: 1px solid {COLOR_BORDER}; display: flex; align-items: center; letter-spacing: 1px; }}
            
            /* 报告内容高亮修复 */
            .box-body {{ padding: 20px; font-size: 14px; line-height: 1.7; color: #ffffff; }} /* 强制白色字体 */
            
            /* 报告内的表格样式 (如果 AI 生成了表格) */
            table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; color: #fff; }}
            th, td {{ border: 1px solid #444; padding: 8px; text-align: left; }}
            th {{ background: #2a2a2a; color: {COLOR_GOLD}; }}
            
            /* 新闻列表 */
            .news-item {{ padding: 6px 0; border-bottom: 1px dashed #333; color: #b0b0b0; font-size: 13px; }}
            .bullet {{ color: {COLOR_GOLD}; margin-right: 8px; font-weight: bold; }}
            
            /* ETF 卡片 */
            .card {{ background: {COLOR_BG_CARD}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; margin-bottom: 15px; overflow: hidden; }}
            .card-header {{ padding: 12px 15px; background: rgba(255,255,255,0.03); border-bottom: 1px solid {COLOR_BORDER}; display: flex; justify-content: space-between; align-items: center; }}
            .card-body {{ padding: 15px; }}
            
            .stock-name {{ font-size: 16px; font-weight: bold; color: #fff; }}
            .stock-code {{ font-size: 13px; color: #aaa; margin-left: 5px; font-family: monospace; }}
            .index-code {{ font-size: 12px; color: #666; margin-left: 5px; }}
            
            /* 徽章 */
            .badge {{ padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
            .buy {{ background: rgba(82,196,26,0.2); color: #73d13d; border: 1px solid #237804; }}
            .sell {{ background: rgba(255,77,79,0.2); color: #ff7875; border: 1px solid #a8071a; }}
            .hold {{ background: rgba(255,255,255,0.05); color: #888; border: 1px solid #444; }}
            
            .tag {{ display: inline-block; background: #262626; border: 1px solid #444; color: #ccc; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-right: 5px; }}
            
            /* 指标 Grid */
            .metrics-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; background: #000; padding: 12px; border-radius: 4px; border: 1px solid #333; font-family: monospace; font-size: 12px; color: #aaa; margin-top: 10px; }}
            .text-red {{ color: #ff4d4f; }} .text-green {{ color: #52c41a; }} .text-white {{ color: #fff; }}
            
            /* AI 角色行 */
            .ai-box {{ margin-top: 15px; font-size: 13px; }}
            .ai-row {{ margin-bottom: 8px; display: flex; align-items: flex-start; color: #ddd; }}
            .role-label {{ font-size: 10px; padding: 2px 5px; border-radius: 3px; margin-right: 8px; width: 35px; text-align: center; flex-shrink: 0; display: inline-block; font-weight: bold; }}
            .cgo {{ background: rgba(82,196,26,0.2); color: {COLOR_GREEN}; }}
            .cro {{ background: rgba(255,77,79,0.2); color: {COLOR_RED}; }}
            .cio {{ background: rgba(255,215,0,0.2); color: {COLOR_GOLD}; }}
            .cio-row {{ background: rgba(255,215,0,0.05); padding: 10px; border-radius: 4px; margin-top: 10px; border-left: 2px solid {COLOR_GOLD}; color: #fff; }}
            
            .footer {{ text-align: center; margin-top: 40px; color: #555; font-size: 11px; border-top: 1px solid #222; padding-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="{logo_src}" style="width:160px; max-width:50%; display:block; margin:0 auto;">
                <div class="title">Magpie Quant System V17.2</div>
            </div>
            
            <div class="box">
                <div class="box-header" style="color:{COLOR_GOLD};">
                    <span style="margin-right:8px;">📡</span> 全球市场快讯
                </div>
                <div class="box-body" style="padding: 15px;">
                    {news_items}
                </div>
            </div>
            
            <div class="box" style="border-top: 3px solid {COLOR_RED};">
                <div class="box-header">
                    <span style="color:{COLOR_RED}; margin-right:8px;">🛑</span> CIO 战略审计报告
                </div>
                <div class="box-body">
                    {cio_content}
                </div>
            </div>
            
            <div class="box" style="border-top: 3px solid {COLOR_GOLD};">
                <div class="box-header">
                    <span style="color:{COLOR_GOLD}; margin-right:8px;">🐦</span> 趋势一致性审计
                </div>
                <div class="box-body">
                    {advisor_content}
                </div>
            </div>
            
            {cards_html}
            
            <div class="footer">
                POWERED BY DEEPSEEK-V3.2 & GEMINI PRO | UI ENGINE V17.2
            </div>
        </div>
    </body>
    </html>"""
