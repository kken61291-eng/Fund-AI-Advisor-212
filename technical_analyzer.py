import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, time as dt_time
from utils import logger, get_beijing_time

class TechnicalAnalyzer:
    def __init__(self):
        pass

    @staticmethod
    def _calculate_trade_minutes(current_time):
        """
        [数学核心] 计算A股当日已交易分钟数 (全天240分钟)
        剔除午休 11:30 - 13:00
        """
        # 转为分钟数方便计算 (hour * 60 + minute)
        t_min = current_time.hour * 60 + current_time.minute
        
        # 关键时间点
        t_open_am = 9 * 60 + 30   # 09:30 (570)
        t_close_am = 11 * 60 + 30 # 11:30 (690)
        t_open_pm = 13 * 60       # 13:00 (780)
        t_close_pm = 15 * 60      # 15:00 (900)
        
        if t_min < t_open_am:
            return 0 # 盘前
        elif t_open_am <= t_min <= t_close_am:
            return t_min - t_open_am # 上午交易时长
        elif t_close_am < t_min < t_open_pm:
            return 120 # 午休期间 (固定为上午的120分钟)
        elif t_open_pm <= t_min <= t_close_pm:
            return 120 + (t_min - t_open_pm) # 上午120 + 下午时长
        else:
            return 240 # 盘后

    @staticmethod
    def calculate_indicators(df):
        if df is None or df.empty or len(df) < 30:
            return {}

        # --- [V14.28 核心] 全时段动态成交量投影 ---
        try:
            last_date = df.index[-1]
            now_bj = get_beijing_time()
            
            # 只有当K线日期是今天，且未收盘时，才进行预测
            if last_date.date() == now_bj.date() and now_bj.time() < dt_time(15, 0):
                
                trade_mins = TechnicalAnalyzer._calculate_trade_minutes(now_bj.time())
                
                # 只有交易超过 15 分钟才开始预测，避免开盘集合竞价噪音太大
                if trade_mins > 15:
                    original_vol = df.iloc[-1]['volume']
                    
                    # 动态乘数 = 全天240分钟 / 已交易分钟
                    # 举例: 10:30运行 (已交易60分) -> 乘数 = 240/60 = 4.0
                    # 举例: 14:20运行 (已交易230分) -> 乘数 = 240/230 = 1.04
                    multiplier = 240 / trade_mins
                    
                    # 稍微打个折(0.95)，因为早盘量通常比盘中大，直接线性外推容易虚高
                    if trade_mins < 120: 
                        multiplier *= 0.9 # 上午保守一点
                    else:
                        multiplier *= 1.05 # 下午通常有尾盘放量，稍微补偿一点
                    
                    projected_vol = original_vol * multiplier
                    
                    # 修改数据
                    vol_idx = df.columns.get_loc('volume')
                    df.iloc[-1, vol_idx] = projected_vol
                    
                    logger.info(f"⚖️ [动态量能投影] 交易{trade_mins}min | 乘数x{multiplier:.2f} | Vol预测: {int(original_vol)} -> {int(projected_vol)}")
                else:
                    logger.info("⏳ [动态量能投影] 开盘时间不足15分钟，跳过预测，暂用实盘量。")
                    
        except Exception as e:
            logger.warning(f"量能投影计算微瑕: {e}")
        # ---------------------------------------

        indicators = {}
        
        try:
            close = df['close']
            volume = df['volume']
            current_price = close.iloc[-1]
            
            # RSI
            rsi = ta.rsi(close, length=14)
            indicators['rsi'] = round(rsi.iloc[-1], 2)

            # MACD
            macd = ta.macd(close, fast=12, slow=26, signal=9)
            macd_hist = macd['MACDh_12_26_9'].iloc[-1]
            
            # Trend
            if macd_hist > 0 and macd_hist < macd['MACDh_12_26_9'].iloc[-2]:
                macd_trend = "红柱缩短"
            elif macd_hist < 0 and macd_hist > macd['MACDh_12_26_9'].iloc[-2]:
                macd_trend = "绿柱缩短"
            else:
                macd_trend = "金叉" if macd_hist > 0 else "死叉"
                
            indicators['macd'] = {
                "trend": macd_trend,
                "hist": round(macd_hist, 3)
            }

            # Bollinger
            bb = ta.bbands(close, length=20, std=2)
            pct_b = bb['BBP_20_2.0'].iloc[-1]
            indicators['risk_factors'] = {
                "bollinger_pct_b": round(pct_b, 2)
            }

            # VR & OBV
            ma_vol_5 = volume.rolling(window=5).mean().iloc[-1]
            vol_ratio = volume.iloc[-1] / ma_vol_5 if ma_vol_5 > 0 else 1.0
            
            obv = ta.obv(close, volume)
            obv_slope = (obv.iloc[-1] - obv.iloc[-10]) / 10 if len(obv) > 10 else 0
            
            indicators['flow'] = {
                "obv_slope": round(obv_slope / 10000, 2)
            }
            indicators['risk_factors']['vol_ratio'] = round(vol_ratio, 2)

            # Weekly Trend
            df_weekly = df.resample('W').agg({'close': 'last'})
            if len(df_weekly) >= 5:
                ma5_weekly = df_weekly['close'].rolling(5).mean().iloc[-1]
                trend_status = "UP" if df_weekly['close'].iloc[-1] > ma5_weekly else "DOWN"
            else:
                trend_status = "Unknown"
            
            indicators['trend_weekly'] = trend_status
            indicators['price'] = current_price

            # Scoring
            score = 50
            if indicators['rsi'] < 30: score += 15
            if indicators['rsi'] > 70: score -= 10
            if macd_hist > 0: score += 10
            if trend_status == "UP": score += 20
            if vol_ratio > 1.2: score += 5
            if vol_ratio < 0.6: score -= 15
            if obv_slope > 0: score += 10
            
            indicators['quant_score'] = max(0, min(100, score))
            
            # CRO Signals
            cro_signal = "PASS"
            cro_reason = "技术指标正常"
            
            if trend_status == "DOWN":
                cro_signal = "WARN"
                cro_reason = "周线趋势向下"
            
            # 经过动态投影后，这里的 VR 是全天预测值
            if vol_ratio < 0.6: 
                cro_signal = "VETO"
                cro_reason = f"流动性枯竭(预测VR {vol_ratio}<0.6)"
            
            if indicators['rsi'] > 85:
                cro_signal = "VETO"
                cro_reason = "RSI极度超买"

            indicators['tech_cro_signal'] = cro_signal
            indicators['tech_cro_comment'] = cro_reason

            return indicators

        except Exception as e:
            logger.error(f"指标计算失败: {e}")
            return {}
