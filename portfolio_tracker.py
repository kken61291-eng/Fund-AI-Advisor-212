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
        default = {"holdings": {}, "pending": []}
        if not os.path.exists(self.file_path): return default
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                try:
                    fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    data = json.load(f)
                    fcntl.flock(f, fcntl.LOCK_UN)
                except: data = json.load(f)
            
            if not isinstance(data, dict): return default
            if "holdings" not in data: data["holdings"] = {}
            if "pending" not in data: data["pending"] = []
            return data
        except: return default

    def save_atomic(self):
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, dir='.', encoding='utf-8') as tmp:
                json.dump(self.data, tmp, indent=4, ensure_ascii=False)
                tmp.flush()
                os.fsync(tmp.fileno())
                shutil.move(tmp.name, self.file_path)
        except Exception as e: logger.error(f"Save failed: {e}")

    def confirm_trades(self):
        today = datetime.now().strftime("%Y-%m-%d")
        new_pending = []
        count = 0
        for trade in self.data.get("pending", []):
            if trade.get("confirm_date", "9999") <= today:
                self._execute(trade)
                count += 1
            else: new_pending.append(trade)
        if count > 0:
            self.data["pending"] = new_pending
            self.save_atomic()
            logger.info(f"✅ 确认 {count} 笔 T+1 交易")

    def _execute(self, trade):
        code = trade["code"]
        amt = trade["amount"]
        price = trade["price"]
        date = trade.get("date", datetime.now().strftime("%Y-%m-%d"))
        
        if code not in self.data["holdings"]:
            self.data["holdings"][code] = {"cost": 0.0, "shares": 0.0, "amount": 0.0, "last_buy_date": date}
        pos = self.data["holdings"][code]
        
        if amt > 0: # Buy
            new_s = amt / price
            tot_s = pos["shares"] + new_s
            tot_c = (pos["shares"] * pos["cost"]) + amt
            pos["cost"] = tot_c / tot_s if tot_s > 0 else 0
            pos["shares"] = round(tot_s, 2)
            pos["amount"] = round(tot_s * pos["cost"], 2)
            pos["last_buy_date"] = date
        else: # Sell
            sell_s = abs(amt)
            pos["shares"] = max(0, round(pos["shares"] - sell_s, 2))
            pos["amount"] = round(pos["shares"] * pos["cost"], 2)
            if pos["shares"] < 10: del self.data["holdings"][code]

    def add_trade(self, code, name, amount, price, is_sell=False):
        c_date = (datetime.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        val = amount
        if is_sell:
            cur_s = self.data["holdings"].get(code, {}).get("shares", 0)
            val = -min(amount/price, cur_s) # 存负份额
            
        self.data["pending"].append({
            "code": code, "name": name, "amount": val, "price": price,
            "date": today, "confirm_date": c_date
        })
        self.save_atomic()

    def get_position(self, code):
        h = self.data["holdings"].get(code, {})
        days = 999
        if "last_buy_date" in h:
            try: days = (pd.to_datetime(datetime.now().strftime("%Y-%m-%d")) - pd.to_datetime(h["last_buy_date"])).days
            except: pass
        return {"cost": h.get("cost", 0.0), "shares": h.get("shares", 0.0), "held_days": days}
