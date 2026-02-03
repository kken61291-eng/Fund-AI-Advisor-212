import json
import os
import fcntl
import tempfile
import shutil
import pandas as pd
from datetime import datetime
from utils import logger

class PortfolioTracker:
    def __init__(self, file_path="portfolio.json"):
        self.file_path = file_path
        self.data = self._load_atomic()

    def _load_atomic(self):
        default_structure = {"holdings": {}, "pending": []}
        if not os.path.exists(self.file_path): return default_structure
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                try:
                    fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    data = json.load(f)
                    fcntl.flock(f, fcntl.LOCK_UN)
                except: data = json.load(f)
            
            if not isinstance(data, dict): return default_structure
            if "holdings" not in data: data["holdings"] = {}
            if "pending" not in data: data["pending"] = []
            return data
        except: return default_structure

    def save_atomic(self):
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, dir='.', encoding='utf-8') as tmp:
                json.dump(self.data, tmp, indent=4, ensure_ascii=False)
                tmp.flush()
                os.fsync(tmp.fileno())
                shutil.move(tmp.name, self.file_path)
        except Exception as e:
            logger.error(f"Save failed: {e}")

    def confirm_trades(self):
        today = datetime.now().strftime("%Y-%m-%d")
        new_pending = []
        confirmed = False
        
        for trade in self.data["pending"]:
            if trade.get("confirm_date", "9999-99-99") <= today:
                self._execute_confirmed_trade(trade)
                confirmed = True
            else:
                new_pending.append(trade)
        
        if confirmed:
            self.data["pending"] = new_pending
            self.save_atomic()

    def _execute_confirmed_trade(self, trade):
        code = trade["code"]
        trade_amt = trade["amount"]
        price = trade["price"]
        date = trade.get("date", datetime.now().strftime("%Y-%m-%d")) # 记录交易发生日

        if code not in self.data["holdings"]:
            self.data["holdings"][code] = {
                "cost": 0.0, "shares": 0.0, "amount": 0.0, 
                "last_buy_date": date # 初始化买入时间
            }
        
        pos = self.data["holdings"][code]
        
        if trade_amt > 0: # 买入
            new_shares = trade_amt / price
            total_shares = pos["shares"] + new_shares
            total_cost_amt = (pos["shares"] * pos["cost"]) + trade_amt
            
            pos["cost"] = total_cost_amt / total_shares if total_shares > 0 else 0
            pos["shares"] = round(total_shares, 2)
            pos["amount"] = round(total_shares * pos["cost"], 2)
            pos["last_buy_date"] = date # 更新最后买入时间
            
        else: # 卖出
            sell_shares = abs(trade_amt)
            pos["shares"] = max(0, round(pos["shares"] - sell_shares, 2))
            pos["amount"] = round(pos["shares"] * pos["cost"], 2)
            if pos["shares"] < 10: del self.data["holdings"][code]

    def add_trade(self, code, name, amount, price, is_sell=False):
        confirm_date = (datetime.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        
        val = amount if not is_sell else -min(amount/price, self.data["holdings"].get(code,{}).get("shares",0))
        
        self.data["pending"].append({
            "code": code, "name": name, "amount": val, "price": price,
            "date": today, "confirm_date": confirm_date
        })
        self.save_atomic()

    def get_position(self, code):
        h = self.data["holdings"].get(code, {})
        # 计算持有天数
        held_days = 0
        if "last_buy_date" in h:
            try:
                last = pd.to_datetime(h["last_buy_date"])
                now = pd.to_datetime(datetime.now().strftime("%Y-%m-%d"))
                held_days = (now - last).days
            except: pass
            
        return {
            "cost": h.get("cost", 0.0),
            "shares": h.get("shares", 0.0),
            "held_days": held_days # 返回持有天数
        }
