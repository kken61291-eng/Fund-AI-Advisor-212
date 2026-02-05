import json
import os
import threading
from datetime import datetime
from utils import logger

class PortfolioTracker:
    def __init__(self, filepath='portfolio.json'):
        self.filepath = filepath
        self.lock = threading.Lock()
        self._load_portfolio()

    def _load_portfolio(self):
        if not os.path.exists(self.filepath):
            self.portfolio = {}
            self._save_portfolio()
        else:
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.portfolio = json.load(f)
            except Exception:
                self.portfolio = {}

    def _save_portfolio(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.portfolio, f, indent=2, ensure_ascii=False)

    def get_position(self, code):
        """获取持仓详情 (兼容旧格式)"""
        if code not in self.portfolio:
            return {'shares': 0, 'cost': 0.0, 'held_days': 0}
        
        pos = self.portfolio[code]
        # 确保关键字段存在
        if 'cost' not in pos: pos['cost'] = 0.0
        if 'shares' not in pos: pos['shares'] = 0
        return pos

    def add_trade(self, code, name, amount_or_value, price, is_sell=False):
        """
        记录交易并自动计算加权平均成本 (Weighted Average Cost)
        """
        if price <= 0: return

        if code not in self.portfolio:
            self.portfolio[code] = {
                "name": name,
                "shares": 0,
                "cost": 0.0,
                "held_days": 0,
                "history": []
            }
        
        pos = self.portfolio[code]
        shares_change = amount_or_value / price
        
        record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "price": round(price, 3),
            "s": "S" if is_sell else "B"
        }

        if is_sell:
            # 卖出逻辑: 成本价不变，份额减少，记录已实现盈亏(可选)
            # 这里简单处理: 减少份额
            real_sell_shares = min(pos['shares'], shares_change) # 防止卖空
            pos['shares'] = max(0, pos['shares'] - real_sell_shares)
            record['amt'] = -int(real_sell_shares * price)
            
            if pos['shares'] == 0:
                pos['cost'] = 0.0 # 清仓后成本归零
                pos['held_days'] = 0
                
        else:
            # 买入逻辑: 核心! 计算加权平均成本
            # 新成本 = (旧总值 + 新买入值) / 新总份额
            old_value = pos['shares'] * pos['cost']
            new_invest = shares_change * price
            total_shares = pos['shares'] + shares_change
            
            if total_shares > 0:
                new_cost = (old_value + new_invest) / total_shares
                pos['cost'] = round(new_cost, 4) # 保留4位小数精度
            
            pos['shares'] = total_shares
            record['amt'] = int(amount_or_value)
            # 买入重置持有天数? 不，累积持有，仅清仓重置
            if pos['held_days'] == 0:
                pos['held_days'] = 1

        # 限制历史记录长度
        pos['history'].append(record)
        if len(pos['history']) > 10:
            pos['history'] = pos['history'][-10:]

        self._save_portfolio()
        logger.info(f"⚖️ 账本更新 {name}: {'卖出' if is_sell else '买入'} | 最新成本: {pos.get('cost',0):.3f}")

    def record_signal(self, code, signal):
        # 仅用于记录信号历史，不涉及资金
        pass # V14 逻辑已将信号记录整合到 HTML，此处可简化

    def get_signal_history(self, code):
        if code in self.portfolio:
            return self.portfolio[code].get('history', [])
        return []
        
    def confirm_trades(self):
        # 每日持有天数 +1
        today = datetime.now().strftime("%Y-%m-%d")
        # 简单防重: 实际生产环境可用文件记录上次运行日期
        for code, pos in self.portfolio.items():
            if pos['shares'] > 0:
                pos['held_days'] = pos.get('held_days', 0) + 1
        self._save_portfolio()
