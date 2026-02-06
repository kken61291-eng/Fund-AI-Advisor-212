import akshare as ak
import pandas as pd
import time
import random
import requests
from datetime import datetime, time as dt_time
from utils import logger, retry, get_beijing_time

try:
    import yfinance as yf
except ImportError:
    yf = None

class DataFetcher:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def _is_trading_time(self):
        now = get_beijing_time()
        if now.weekday() >= 5: return False
        current_time = now.time()
        start = dt_time(9, 30)
        end = dt_time(15, 0)
        return start <= current_time <= end

    def _fetch_realtime_candle(self, code):
        try:
            df_spot = ak.stock_zh_a_spot_em()
            target = df_spot[df_spot['代码'] == code]
            if target.empty: return None
            
            row = target.iloc[0]
            current_close = float(row['最新价'])
            if current_close <= 0: return None

            candle = pd.Series({
                'close': current_close,
                'high': float(row['最高']),
                'low': float(row['最低']),
                'open': float(row['今开']),
                'volume': float(row['成交量']) if '成交量' in row else 0.0,
                'date': get_beijing_time().replace(hour=0, minute=0, second=0, microsecond=0)
            })
            return candle
        except Exception as e:
            # logger.warning(f"实时K线缝合失败 {code}: {e}") # 降低日志噪音
            return None

    @retry(retries=2, delay=3)
    def get_fund_history(self, code, period='3y'):
        time.sleep(random.uniform(1.5, 3.5))
        df_hist = None

        # 1. 尝试 AkShare (东财源 - 首选)
        try:
            df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date="20200101", end_date="20500101")
            if not df.empty:
                df = df.rename(columns={"日期": "date", "收盘": "close", "最高": "high", "最低": "low", "开盘": "open", "成交量": "volume"})
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                if df.index.tz is not None: df.index = df.index.tz_localize(None)
                df_hist = df
        except Exception as e:
            logger.warning(f"东财源受阻 {code}: {str(e)[:50]}")

        # 2. 尝试 AkShare (新浪源 - 备用)
        if df_hist is None or df_hist.empty:
            try:
                time.sleep(2)
                symbol = f"sh{code}" if code.startswith('5') or code.startswith('6') else f"sz{code}"
                # 新浪接口通常更稳
                df = ak.stock_zh_index_daily(symbol=symbol)
                if not df.empty:
                    df = df.rename(columns={"date": "date", "close": "close", "high": "high", "low": "low", "open": "open", "volume": "volume"})
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                    if df.index.tz is not None: df.index = df.index.tz_localize(None)
                    df_hist = df
                    logger.info(f"🔄 [备用源] 新浪接力成功: {code}")
            except Exception:
                pass

        # 3. 兜底 Yahoo Finance
        if (df_hist is None or df_hist.empty) and yf:
            try:
                time.sleep(2)
                suffix = ".SS" if code.startswith('5') or code.startswith('6') else ".SZ"
                symbol = code + suffix
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="2y")
                if not df.empty:
                    df = df.rename(columns={"Close": "close", "High": "high", "Low": "low", "Open": "open", "Volume": "volume"})
                    if df.index.tz is not None: df.index = df.index.tz_localize(None)
                    df_hist = df
                    logger.info(f"🌍 [国际源] Yahoo接力成功: {code}")
            except Exception as e:
                logger.error(f"Yahoo 获取失败 {code}: {e}")

        if df_hist is None or df_hist.empty:
            return None

        # 实时缝合逻辑 (保持不变)
        if self._is_trading_time():
            real_candle = self._fetch_realtime_candle(code)
            if real_candle is not None:
                last_date = df_hist.index[-1]
                today_date = pd.Timestamp(real_candle['date'])
                
                if last_date != today_date:
                    df_real = pd.DataFrame([real_candle]).set_index('date')
                    df_hist = pd.concat([df_hist, df_real])
                    logger.info(f"✅ 缝合成功! 当前价: {real_candle['close']}")
                else:
                    df_hist.iloc[-1] = real_candle
                    logger.info(f"✅ 更新今日收盘! 收盘价: {real_candle['close']}")

        return df_hist
