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
        # 伪装头
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def _is_trading_time(self):
        """判断当前是否为A股盘中时间 (09:30 - 15:00)"""
        now = get_beijing_time()
        # 周末不交易
        if now.weekday() >= 5: return False
        
        current_time = now.time()
        start = dt_time(9, 30)
        end = dt_time(15, 0) # 15:00前都算盘中
        return start <= current_time <= end

    def _fetch_realtime_candle(self, code):
        """
        [核心黑科技] 获取当天的实时行情，并伪装成一根日K线
        """
        try:
            # 获取东财实时行情 (虽然数据量大，但包含OHLC完整数据)
            # 注意：这个接口返回所有A股/ETF，我们需要过滤
            df_spot = ak.stock_zh_a_spot_em()
            
            # 过滤出当前标的
            # 东财的spot接口代码通常没有前缀，或者我们需要匹配
            target = df_spot[df_spot['代码'] == code]
            
            if target.empty:
                return None
            
            # 提取数据
            row = target.iloc[0]
            
            # 构造一根 K 线 Series
            # 格式需与 get_fund_history 返回的 DataFrame 列名一致
            # {"date", "close", "high", "low", "open", "volume"}
            
            current_close = float(row['最新价'])
            if current_close <= 0: return None # 停牌或异常

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
            logger.warning(f"实时K线缝合失败 {code}: {e}")
            return None

    @retry(retries=2, delay=3)
    def get_fund_history(self, code, period='3y'):
        """
        获取基金/股票历史数据 (包含实时缝合逻辑)
        """
        time.sleep(random.uniform(1.5, 3.5))

        # 1. 获取历史数据 (T-1)
        df_hist = None
        try:
            # akshare 接口处理
            symbol = code
            if not code.startswith('sh') and not code.startswith('sz'):
                symbol = f"sh{code}" if code.startswith('5') or code.startswith('6') else f"sz{code}"
            
            # 这里的 end_date 设置得很远，但只能取到昨天收盘
            df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date="20200101", end_date="20500101")
            
            if not df.empty:
                df = df.rename(columns={"日期": "date", "收盘": "close", "最高": "high", "最低": "low", "开盘": "open", "成交量": "volume"})
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                if df.index.tz is not None: df.index = df.index.tz_localize(None)
                df_hist = df
                
        except Exception as e:
            logger.warning(f"历史数据获取微瑕 {code}: {str(e)[:50]}")

        # 如果连历史数据都没有，直接返回None
        if df_hist is None or df_hist.empty:
            return None

        # 2. [V14.24 核心] 实时缝合逻辑
        # 如果是盘中 (09:30-15:00)，尝试获取今日实时数据并拼接到最后
        if self._is_trading_time():
            logger.info(f"⚡ 正在缝合今日实时K线: {code}...")
            real_candle = self._fetch_realtime_candle(code)
            
            if real_candle is not None:
                # 检查历史数据最后一天是否已经是今天（防止接口突然更新了重复拼接）
                last_date = df_hist.index[-1]
                today_date = pd.Timestamp(real_candle['date'])
                
                if last_date != today_date:
                    # 转换 Series 为 DataFrame 行并拼接
                    df_real = pd.DataFrame([real_candle]).set_index('date')
                    df_hist = pd.concat([df_hist, df_real])
                    logger.info(f"✅ 缝合成功! 当前价: {real_candle['close']}")
                else:
                    # 如果历史数据里已经有今天了（比如15:30运行），直接更新最后一行
                    df_hist.iloc[-1] = real_candle
                    logger.info(f"✅ 更新今日收盘数据! 收盘价: {real_candle['close']}")

        return df_hist
