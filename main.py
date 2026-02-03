import time
from data_fetcher import DataFetcher
from technical_analyzer import TechnicalAnalyzer
from market_scanner import MarketScanner
from news_analyst import NewsAnalyst
# ... 导入其他 ...

def main():
    # ... 初始化 ...
    
    # 1. 宏观扫描
    market_ctx = scanner.get_market_sentiment()
    
    results = []
    
    # 2. 循环分析 (Map)
    for fund in config['funds']:
        logger.info(f">>> 分析 {fund['name']}...")
        
        # A. 数据获取 (双源 + Resample)
        data = fetcher.get_fund_data_v4(fund['code'], fund['type'])
        
        # B. Python 数学计算 (完全不消耗 Token)
        daily_indicators = TechnicalAnalyzer.calculate_indicators(data['daily_df'])
        weekly_trend = TechnicalAnalyzer.check_weekly_trend(data['weekly_df'])
        
        # 合并指标
        tech_packet = {
            **daily_indicators,
            "weekly_trend": weekly_trend,
            "premium": data['realtime_premium']
        }
        
        # C. 策略规则前置过滤 (Python 侧风控)
        # 如果溢价率过高，直接跳过 AI，节省一次 API 调用
        if tech_packet['premium'] > 3.0:
            logger.warning(f"{fund['name']} 溢价率过高，触发硬风控，跳过 AI 分析")
            results.append({"name": fund['name'], "action": "卖出/观望", "reason": "高溢价风控"})
            continue
            
        # D. AI 逻辑推理 (消耗 Token)
        news = analyst.fetch_news(fund['sector_keyword'])
        ai_decision = analyst.analyze_fund(fund, tech_packet, market_ctx, news)
        
        results.append(ai_decision)
        
        # E. 冷却 (防 429)
        time.sleep(10)

    # 3. 生成报告 & 发送
    # ... 渲染 HTML ...
