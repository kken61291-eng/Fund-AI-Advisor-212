import yaml
import os
import time
from data_fetcher import DataFetcher
from news_analyst import NewsAnalyst
from strategy import StrategyEngine
from utils import push_notification, logger

def load_config():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def main():
    logger.info("========== 基金 AI 投顾启动 ==========")
    
    # 1. 初始化
    config = load_config()
    fetcher = DataFetcher()
    
    # 尝试初始化 AI，失败则降级为纯技术分析
    try:
        analyst = NewsAnalyst()
        ai_enabled = True
    except Exception as e:
        logger.warning(f"AI 分析师初始化失败: {e}，将仅使用技术分析")
        analyst = None
        ai_enabled = False

    engine = StrategyEngine(config)
    
    reports = []
    total_amount = 0
    
    # 2. 遍历基金
    for i, fund in enumerate(config['funds']):
        try:
            logger.info(f"=== 分析 {fund['name']} [{i+1}/{len(config['funds'])}] ===")
            
            # A. 获取技术数据（传入类型）
            fund_type = fund.get('type', 'fund')
            tech_data = fetcher.get_fund_history(fund['code'], fund_type)
            
            # B. 获取新闻与情绪（如果启用）
            if ai_enabled:
                titles = analyst.fetch_news_titles(fund['sector_keyword'])
                s_score, s_summary = analyst.analyze_sentiment(fund['sector_keyword'], titles)
                # 添加延迟避免限流
                if i < len(config['funds']) - 1:
                    time.sleep(2)
            else:
                s_score, s_summary = 5, "AI未启用"
            
            # C. 生成策略
            advice = engine.evaluate(fund, tech_data, s_score, s_summary)
            reports.append(advice)
            
            # 累加建议金额（简单解析）
            if "金额**: ¥" in advice:
                try:
                    amt_str = advice.split("金额**: ¥")[1].split(" ")[0]
                    total_amount += int(amt_str)
                except:
                    pass
            
        except Exception as e:
            logger.error(f"分析 {fund['name']} 时出错: {e}")
            reports.append(f"⚠️ **{fund['name']}**: 分析失败 - {str(e)}")

    # 3. 组装报告
    header = f"""
🚀 **每日基金 AI 投顾报告** 🚀
📅 {time.strftime('%Y-%m-%d %H:%M')}
💰 今日建议总投入: ¥{total_amount} (上限: ¥{config['global']['max_daily_invest']})
{'🤖 AI情绪分析已启用' if ai_enabled else '⚙️ 纯技术分析模式'}
{'='*40}
"""
    
    full_report = header + "\n\n" + "\n\n".join(reports)
    
    # 4. 输出与推送
    print(full_report)
    
    push_token = os.getenv("PUSHPLUS_TOKEN")
    if push_token:
        # 检查是否超过每日上限
        if total_amount > config['global']['max_daily_invest']:
            full_report += f"\n\n⚠️ **提醒**: 建议总金额(¥{total_amount})超过单日上限(¥{config['global']['max_daily_invest']})，请酌情调整"
        
        push_notification("今日基金操作建议", full_report, push_token)
    else:
        logger.info("未配置 PUSHPLUS_TOKEN，仅本地输出")

if __name__ == "__main__":
    main()