def render_html_report(market_ctx, funds_results, daily_total_cap):
    """
    ✨ V9.1 UI: 鎏金量化·核心卫星智投系统
    """
    invested = sum(r['amount'] for r in funds_results if r['amount'] > 0)
    cash_display = f"{invested:,}"
    
    cores = [r for r in funds_results if r['strategy_type'] == 'core']
    sats = [r for r in funds_results if r['strategy_type'] == 'satellite']
    
    def render_group(title, items):
        if not items: return ""
        html_chunk = f'<div class="section-title">{title}</div>'
        for r in items:
            border_color = "#444" 
            if r['amount'] > 0: border_color = "#ff4d4f" 
            elif r.get('is_sell'): border_color = "#52c41a" 
            
            if r['amount'] > 0: 
                act_text = f"<span style='color:#ff4d4f'>+¥{r['amount']:,}</span>"
            elif r.get('is_sell'): 
                act_text = f"<span style='color:#52c41a'>卖出 ¥{int(r.get('sell_value',0)):,}</span>"
            else: 
                act_text = "<span style='color:#888'>持仓/观望</span>"

            ai_html = ""
            if r.get('ai_analysis') and r['ai_analysis'].get('comment'):
                 ai_html = f'<div class="ai-comment"><span class="ai-label">AI:</span>{r["ai_analysis"]["comment"]}</div>'

            html_chunk += f"""
            <div class="card" style="border-left: 3px solid {border_color};">
                <div class="card-header">
                    <div>
                        <span class="fund-name">{r['name']}</span>
                        <span class="fund-code">{r['code']}</span>
                    </div>
                    <div class="fund-action">{r['position_type']}</div>
                </div>
                
                <div class="card-body">
                    <div class="row">
                        <span>操作: {act_text}</span>
                        <span>评分: <b style="color:#D4AF37">{r['tech']['quant_score']}</b></span>
                    </div>
                    <div class="metrics">
                        <span>RSI: {r['tech']['rsi']}</span>
                        <span>Bias: {r['tech']['bias_20']}%</span>
                        <span>周线: {r['tech']['trend_weekly']}</span>
                    </div>
                    <div class="tags">
                        {''.join([f'<span class="tag">{x}</span>' for x in r['tech']['quant_reasons']])}
                    </div>
                    {ai_html}
                </div>
            </div>
            """
        return html_chunk

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                background-color: #000000; color: #e0e0e0;
                font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif;
                margin: 0; padding: 20px;
            }}
            .container {{
                max-width: 600px; margin: 0 auto;
                background: #111111; border: 1px solid #333;
                border-radius: 10px; overflow: hidden;
            }}
            .header {{
                background: linear-gradient(180deg, #1a1a1a 0%, #111111 100%);
                padding: 30px; text-align: center;
                border-bottom: 2px solid #D4AF37; /* 鎏金分割线 */
            }}
            .title {{ 
                font-size: 26px; color: #D4AF37; margin: 0; font-weight: bold; 
                letter-spacing: 1px; text-transform: uppercase;
                background: linear-gradient(to right, #D4AF37, #FCEabb, #D4AF37);
                -webkit-background-clip: text; color: transparent;
            }}
            .subtitle {{ color: #666; font-size: 12px; margin-top: 8px; letter-spacing: 1px; }}
            
            .dashboard {{ padding: 20px; text-align: center; border-bottom: 1px solid #222; }}
            .money {{ font-size: 32px; color: #fff; font-weight: bold; margin: 10px 0; }}
            .macro {{ font-size: 12px; color: #888; }}
            
            .section-title {{
                padding: 15px 20px; color: #D4AF37; font-size: 14px;
                background: #0a0a0a; border-top: 1px solid #222; border-bottom: 1px solid #222;
                letter-spacing: 1px;
            }}
            
            .card {{
                margin: 15px 20px; background: #1c1c1c; 
                border-radius: 6px; overflow: hidden;
                box-shadow: 0 2px 5px rgba(0,0,0,0.5);
            }}
            .card-header {{
                padding: 12px 15px; background: #252525;
                display: flex; justify-content: space-between; align-items: center;
            }}
            .fund-name {{ font-size: 15px; font-weight: bold; color: #fff; }}
            .fund-code {{ font-size: 12px; color: #666; margin-left: 5px; }}
            .fund-action {{ font-size: 12px; color: #D4AF37; font-weight: bold; }}
            
            .card-body {{ padding: 15px; color: #ccc; }}
            .row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px; }}
            .metrics {{ font-size: 11px; color: #666; margin-bottom: 10px; font-family: monospace; }}
            .metrics span {{ margin-right: 10px; }}
            
            .tags {{ margin-bottom: 5px; }}
            .tag {{ 
                display: inline-block; background: #333; color: #aaa; 
                padding: 2px 6px; border-radius: 3px; font-size: 10px; 
                margin-right: 5px; margin-bottom: 3px; border: 1px solid #444; 
            }}
            
            .ai-comment {{ 
                margin-top: 10px; padding: 10px; background: #0f0f0f; 
                border: 1px dashed #444; border-radius: 4px;
                color: #999; font-size: 12px; font-style: italic; line-height: 1.5;
            }}
            .ai-label {{ color: #D4AF37; margin-right: 5px; font-style: normal; font-weight:bold; }}
            
            .footer {{ padding: 25px; text-align: center; color: #444; font-size: 11px; background: #0a0a0a; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="title">鎏金量化 · 核心卫星智投</div>
                <div class="subtitle">GILDED QUANT SYSTEM | V9.1 FINAL EDITION</div>
                <div style="font-size:10px; color:#555; margin-top:5px;">{datetime.now().strftime('%Y-%m-%d')}</div>
            </div>
            
            <div class="dashboard">
                <div class="macro">Market Context: {market_ctx.get('north_label')} {market_ctx.get('north_money')}</div>
                <div style="color:#888; font-size:12px; margin-top:10px;">建议投入 (CNY)</div>
                <div class="money">¥{cash_display}</div>
            </div>
            
            {render_group("🪐 核心资产 (底仓/定投)", cores)}
            {render_group("🚀 卫星资产 (波段/轮动)", sats)}
            
            <div class="footer">
                <strong>SYSTEM STATUS: OPERATIONAL</strong><br>
                Core Assets: Long-term Hold | Satellite Assets: Swing Trade<br>
                Powered by Kimi AI & Quantitative Math
            </div>
        </div>
    </body></html>
    """
    return html
