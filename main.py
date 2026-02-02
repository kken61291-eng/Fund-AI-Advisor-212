import yaml
import os
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
from market_scanner import MarketScanner # 新增
from strategy import StrategyEngine
from utils import send_email, logger

def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def main():
    config = load_config()
    fetcher = DataFetcher()
    scanner = MarketScanner() # 新增雷达
    engine = StrategyEngine(config)
    
    # 容错初始化 AI
    analyst = None
    try:
        analyst = NewsAnalyst()
    except Exception as e:
        logger.error(f"AI 初始化失败: {e}")

    report = "🚀 **Fund-AI V2.0 深度投顾报告** 🚀\n"
    report += f"📅 日期: {os.popen('date').read().strip()}\n\n"
    
    # --- STEP 1: 全市场扫描 ---
    logger.info(">>> 启动全市场扫描...")
    market_ctx = scanner.get_market_sentiment()
    
    report += "🌍 **宏观与主力风向**\n"
    report += f"• 北向资金(聪明钱): {market_ctx['north_label']} ({market_ctx['north_money']}亿)\n"
    report += f"• 主力抢筹板块 Top5: {', '.join(market_ctx['top_sectors'])}\n"
    report += "--------------------------------\n\n"

    # --- STEP 2: 个基深度分析 ---
    for fund in config['funds']:
        try:
            logger.info(f"=== 深度分析 {fund['name']} ===")
            
            # A. 技术面
            tech_data = fetcher.get_fund_history(fund['code'])
            
            # B. 消息面 + AI逻辑推演
            ai_result = {}
            if analyst:
                titles = analyst.fetch_news_titles(fund['sector_keyword'])
                # 传入宏观数据和技术数据，让AI综合思考
                ai_result = analyst.deep_analysis(
                    fund['name'], 
                    fund['sector_keyword'], 
                    titles, 
                    market_ctx, 
                    tech_data
                )
            
            # C. 策略生成
            advice = engine.calculate_final_decision(fund, tech_data, ai_result, market_ctx)
            report += advice + "\n------------------\n"
            
        except Exception as e:
            logger.error(f"分析 {fund['name']} 失败: {e}")
            report += f"⚠️ {fund['name']} 分析中断: {e}\n"

    print(report)
    try:
        send_email("今日基金深度策略 (V2.0)", report)
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")

if __name__ == "__main__":
    main()
