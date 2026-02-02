import yaml
import os
import time  # 引入时间库，用于限流
from datetime import datetime
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
from market_scanner import MarketScanner
from strategy import StrategyEngine
from utils import send_email, logger

def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def render_html_report(market_ctx, funds_results):
    """
    【UI核心】生成漂亮的 HTML 邮件内容
    """
    # 定义颜色
    COLOR_RED = "#d32f2f"
    COLOR_GREEN = "#2e7d32"
    COLOR_GRAY = "#616161"
    BG_COLOR = "#f5f5f5"
    
    # --- 1. 宏观头部数据处理 (修复类型报错) ---
    north_val = market_ctx.get('north_money', 0)
    
    # 【关键修复】智能转换类型，防止字符串和数字比较报错
    try:
        if isinstance(north_val, str):
            # 如果是 "1.25%" 这种字符串，去掉百分号转数字
            check_val = float(north_val.replace('%', ''))
        else:
            check_val = float(north_val)
    except:
        check_val = 0

    north_color = COLOR_RED if check_val > 0 else COLOR_GREEN
    north_bg = "#ffebee" if check_val > 0 else "#e8f5e9"
    
    # 开始构建 HTML
    html = f"""
    <html>
    <body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: {BG_COLOR}; margin: 0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <div style="background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 20px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px;">🚀 AI 深度投顾日报</h1>
                <p style="margin: 5px 0 0; opacity: 0.8; font-size: 14px;">{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
            </div>

            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <h3 style="margin-top: 0; color: #333;">🌍 市场风向标</h3>
                <div style="display: flex; gap: 10px;">
                    <div style="flex: 1; background-color: {north_bg}; padding: 10px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 12px; color: #666;">{market_ctx.get('north_label', '宏观数据')}</div>
                        <div style="font-size: 20px; font-weight: bold; color: {north_color};">
                            {north_val}
                            <span style="font-size: 12px;">{'' if isinstance(north_val, str) else '亿'}</span>
                        </div>
                    </div>
                    <div style="flex: 1; background-color: #e3f2fd; padding: 10px; border-radius: 8px;">
                        <div style="font-size: 12px; color: #666; text-align: center;">领涨板块 Top5</div>
                        <div style="font-size: 12px; color: #1565c0; margin-top: 5px; line-height: 1.4; text-align: center;">
                            {'<br>'.join(market_ctx.get('top_sectors', ['暂无数据'])[:3])}
                        </div>
                    </div>
                </div>
            </div>
    """

    for res in funds_results:
        action = res['action']
        if "买" in action:
            card_color = COLOR_RED
            btn_bg = "#ffebee"
        elif "卖" in action:
            card_color = COLOR_GREEN
            btn_bg = "#e8f5e9"
        else:
            card_color = COLOR_GRAY
            btn_bg = "#f5f5f5"

        html += f"""
            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <div>
                        <h3 style="margin: 0; color: #333; font-size: 18px;">{res['name']}</h3>
                        <span style="font-size: 12px; color: #999;">{res['code']}</span>
                    </div>
                    <div style="background-color: {card_color}; color: white; padding: 5px 12px; border-radius: 20px; font-weight: bold; font-size: 14px;">
                        {action}
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px;">
                    <div style="background-color: {btn_bg}; padding: 8px; border-radius: 6px;">
                        <span style="display: block; font-size: 12px; color: #666;">建议金额</span>
                        <span style="font-weight: bold; color: {card_color}; font-size: 16px;">¥{int(res['amount'])}</span>
                    </div>
                    <div style="background-color: #f9f9f9; padding: 8px; border-radius: 6px;">
                        <span style="display: block; font-size: 12px; color: #666;">技术指标 (RSI)</span>
                        <span style="font-weight: bold; color: #333; font-size: 16px;">{res['tech']['rsi']:.1f}</span>
                        <span style="font-size: 12px; color: #999;">({res['tech']['price_position']})</span>
                    </div>
                </div>

                <div style="background-color: #fff8e1; border-left: 4px solid #ffc107; padding: 10px; border-radius: 4px; margin-bottom: 10px;">
                    <strong style="color: #f57f17; font-size: 12px;">🧠 AI 核心逻辑:</strong>
                    <p style="margin: 5px 0 0; font-size: 14px; color: #444; line-height: 1.5;">
                        {res['ai']['thesis']}
                    </p>
                </div>

                <div style="font-size: 12px; color: #666; line-height: 1.6;">
                    <div style="margin-bottom: 4px;">📈 <span style="color: {COLOR_RED};">利多:</span> {res['ai'].get('pros', 'N/A')}</div>
                    <div>📉 <span style="color: {COLOR_GREEN};">利空:</span> {res['ai'].get('cons', 'N/A')}</div>
                </div>
            </div>
        """

    html += """
            <div style="background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #999;">
                <p style="margin: 0;">此报告由 GitHub Actions + Gemini 2.5 自动生成</p>
                <p style="margin: 5px 0 0;">⚠️ 投资有风险，决策需谨慎</p>
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
    engine = StrategyEngine(config)
    
    analyst = None
    try:
        analyst = NewsAnalyst()
    except Exception as e:
        logger.error(f"AI 初始化失败: {e}")

    # 1. 扫描市场
    logger.info(">>> 启动全市场扫描...")
    market_ctx = scanner.get_market_sentiment()
    funds_results = []

    # 2. 分析基金
    for fund in config['funds']:
        try:
            logger.info(f"=== 深度分析 {fund['name']} ===")
            tech_data = fetcher.get_fund_history(fund['code'])
            
            ai_result = {"thesis": "AI 未启动或限流", "action_advice": "观望", "pros": "N/A", "cons": "N/A"}
            
            if analyst:
                try:
                    titles = analyst.fetch_news_titles(fund['sector_keyword'])
                    ai_result = analyst.deep_analysis(
                        fund['name'], 
                        fund['sector_keyword'], 
                        titles, 
                        market_ctx, 
                        tech_data
                    )
                except Exception as ai_e:
                    logger.error(f"AI 分析单项失败: {ai_e}")
            
            # 策略计算
            action = ai_result.get('action_advice', '观望')
            base_amt = config['global']['base_invest_amount']
            final_amt = 0
            if "买" in action:
                final_amt = base_amt
                if "强力" in action: final_amt *= 1.2
            
            funds_results.append({
                "name": fund['name'],
                "code": fund['code'],
                "action": action,
                "amount": final_amt,
                "tech": tech_data,
                "ai": ai_result
            })

            # 【关键修改】每次请求后强制休眠 15 秒
            # 避免触发 Gemini 免费版每分钟请求限制 (429 Quota Exceeded)
            logger.info("💤 冷却 15 秒以防 API 限流...")
            time.sleep(15)
            
        except Exception as e:
            logger.error(f"分析 {fund['name']} 失败: {e}")

    # 3. 生成并发送
    if funds_results:
        try:
            html_report = render_html_report(market_ctx, funds_results)
            print("HTML 报告生成完毕，准备发送...")
            send_email("📊 AI 深度投顾日报 (修复版)", html_report)
        except Exception as e:
            logger.error(f"报告生成或发送失败: {e}")

if __name__ == "__main__":
    main()
