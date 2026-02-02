class StrategyEngine:
    def __init__(self, config):
        self.cfg = config
        self.base_amt = config['global']['base_invest_amount']
        self.max_daily = config['global']['max_daily_invest']
    
    def evaluate(self, fund_info, tech_data, sentiment_score, sentiment_summary):
        """
        核心决策逻辑：技术面 + 情绪面 + 资金管理
        """
        rsi = tech_data.get('rsi', 50)
        price_pos = tech_data.get('price_position', 'bear')
        deviation = tech_data.get('ma_deviation', 0)  # 偏离度
        
        action = "观望"
        amount = 0
        reason = []
        risk_level = "低"

        # --- 1. 极端超卖逻辑（左侧交易）---
        if rsi < self.cfg['strategy']['rsi_buy_threshold']:
            if sentiment_score >= 4:
                action = "买入 (超卖反弹)"
                # 超卖越严重，买入倍数越高（最多2倍）
                multiplier = min(2.0, 1.0 + (35 - rsi) / 35)
                amount = self.base_amt * multiplier
                reason.append(f"RSI({rsi:.1f})极度超卖，情绪正常({sentiment_score}分)，建议分批抄底")
                risk_level = "中"
            else:
                action = "小额试探"
                amount = self.base_amt * 0.3
                reason.append(f"超卖但情绪悲观({sentiment_score}分)，极小仓位试探或观望")

        # --- 2. 趋势确认逻辑（右侧交易）---
        elif price_pos == 'bull' and rsi < 65:
            if sentiment_score >= 7:
                action = "买入 (趋势确认)"
                amount = self.base_amt * 1.2
                reason.append(f"站上20日均线(+{deviation:.1f}%)，情绪利好，顺势加仓")
            elif sentiment_score >= 5:
                action = "常规定投"
                amount = self.base_amt
                reason.append("趋势向上但情绪中性，常规定投")

        # --- 3. 止盈/风险控制逻辑---
        elif rsi > self.cfg['strategy']['rsi_sell_threshold']:
            action = "减仓/暂停"
            amount = 0
            reason.append(f"RSI({rsi:.1f})超买，且偏离均线{deviation:.1f}%，建议止盈或暂停定投")
            risk_level = "高"
            
        # --- 4. 均线下方积累逻辑 ---
        elif price_pos == 'bear' and abs(deviation) < 5:
            # 价格在均线下方但偏离不大，且情绪不崩
            if sentiment_score >= 5:
                action = "常规定投"
                amount = self.base_amt
                reason.append("震荡区间，坚持定投积累筹码")
            else:
                action = "暂停/观望"
                reason.append(f"震荡但情绪偏弱({sentiment_score}分)，暂缓投入")

        else:
            reason.append("信号不明确，建议观望")

        # --- 资金风控 ---
        if amount > self.base_amt * 1.5:
            risk_level = "高"
        elif amount > self.base_amt:
            risk_level = "中"

        # 生成报告
        emoji_map = {"买入 (超卖反弹)": "🔥", "买入 (趋势确认)": "📈", "减仓/暂停": "⚠️", 
                     "观望": "⏸️", "常规定投": "🔄", "小额试探": "🧪", "暂停/观望": "🛑"}
        
        icon = emoji_map.get(action, "⏸️")
        
        report = f"""
**{icon} {fund_info['name']} ({fund_info['code']})**
- **操作**: {action} | **金额**: ¥{int(amount)} | **风险**: {risk_level}
- **AI情绪**: {sentiment_summary} ({sentiment_score}/10)
- **技术面**: RSI={rsi:.1f} | 趋势={'多头📈' if price_pos=='bull' else '空头📉'} | 偏离MA20: {deviation:.1f}%
- **逻辑**: {'; '.join(reason)}
"""
        return report.strip()