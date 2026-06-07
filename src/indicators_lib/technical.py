"""Core technical indicators implementation."""

import numpy as np
import pandas as pd
from typing import List, Optional, Dict, Any
from .types import Kline, BollingerBands, MACD, Stochastic, IndicatorConfig


class TechnicalIndicators:
    """Professional-grade technical indicator calculations."""
    
    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> List[float]:
        """Simple Moving Average."""
        if len(prices) < period:
            return [np.nan] * len(prices)
        
        result = []
        for i in range(len(prices)):
            if i < period - 1:
                result.append(np.nan)
            else:
                result.append(np.mean(prices[i - period + 1:i + 1]))
        return result
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[float]:
        """Exponential Moving Average."""
        if len(prices) < period:
            return [np.nan] * len(prices)
        
        alpha = 2.0 / (period + 1)
        result = []
        
        # Initialize with SMA
        sma_value = np.mean(prices[:period])
        result.extend([np.nan] * (period - 1))
        result.append(sma_value)
        
        # Calculate EMA
        for i in range(period, len(prices)):
            ema_value = alpha * prices[i] + (1 - alpha) * result[-1]
            result.append(ema_value)
        
        return result
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
        """Relative Strength Index."""
        if len(prices) <= period:
            return [np.nan] * len(prices)
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        rsi_values = [np.nan] * (period)
        
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))
        
        # Calculate subsequent RSI values using Wilder's smoothing
        for i in range(period + 1, len(prices)):
            gain = gains[i - 1] if i - 1 < len(gains) else 0
            loss = losses[i - 1] if i - 1 < len(losses) else 0
            
            avg_gain = ((avg_gain * (period - 1)) + gain) / period
            avg_loss = ((avg_loss * (period - 1)) + loss) / period
            
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))
        
        return rsi_values
    
    @staticmethod
    def calculate_atr(klines: List[Kline], period: int = 14) -> List[float]:
        """Average True Range."""
        if len(klines) < period + 1:
            return [np.nan] * len(klines)

        true_ranges = []
        for i in range(1, len(klines)):
            high_low = klines[i].high - klines[i].low
            high_close_prev = abs(klines[i].high - klines[i - 1].close)
            low_close_prev = abs(klines[i].low - klines[i - 1].close)

            true_range = max(high_low, high_close_prev, low_close_prev)
            true_ranges.append(true_range)

        atr_values = [np.nan] * len(klines)
        if len(true_ranges) >= period:
            initial_atr = np.mean(true_ranges[:period])
            atr_values[period] = initial_atr

            # Wilder's smoothing for subsequent values
            for i in range(period + 1, len(klines)):
                tr_index = i - 1
                prev_atr = atr_values[i - 1]
                atr_values[i] = ((prev_atr * (period - 1)) + true_ranges[tr_index]) / period

        return atr_values
    
    @staticmethod
    def calculate_bollinger_bands(klines: List[Kline], period: int = 20, std_dev: float = 2.0) -> BollingerBands:
        """Bollinger Bands calculation."""
        prices = [k.close for k in klines]
        
        if len(prices) < period:
            return BollingerBands(
                upper_band=[np.nan] * len(prices),
                middle_band=[np.nan] * len(prices),
                lower_band=[np.nan] * len(prices),
                bandwidth=[np.nan] * len(prices),
                bb_position=[np.nan] * len(prices)
            )
        
        sma = TechnicalIndicators.calculate_sma(prices, period)
        
        std_values = []
        for i in range(len(prices)):
            if i < period - 1:
                std_values.append(np.nan)
            else:
                std_val = np.std(prices[i - period + 1:i + 1], ddof=0)
                std_values.append(std_val)
        
        upper_band = [sma[i] + (std_dev * std_values[i]) if not np.isnan(sma[i]) else np.nan 
                      for i in range(len(sma))]
        lower_band = [sma[i] - (std_dev * std_values[i]) if not np.isnan(sma[i]) else np.nan 
                      for i in range(len(sma))]
        
        # Calculate bandwidth and position
        bandwidth = [(upper_band[i] - lower_band[i]) / sma[i] * 100 
                     if not np.isnan(upper_band[i]) and sma[i] != 0 else np.nan 
                     for i in range(len(upper_band))]
        
        bb_position = [(prices[i] - lower_band[i]) / (upper_band[i] - lower_band[i]) * 100
                       if not np.isnan(upper_band[i]) and (upper_band[i] - lower_band[i]) != 0 else np.nan
                       for i in range(len(prices))]
        
        return BollingerBands(
            upper_band=upper_band,
            middle_band=sma,
            lower_band=lower_band,
            bandwidth=bandwidth,
            bb_position=bb_position
        )
    
    @staticmethod
    def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> MACD:
        """MACD calculation."""
        if len(prices) < slow:
            return MACD(
                macd_line=[np.nan] * len(prices),
                signal_line=[np.nan] * len(prices),
                histogram=[np.nan] * len(prices)
            )
        
        ema_fast = TechnicalIndicators.calculate_ema(prices, fast)
        ema_slow = TechnicalIndicators.calculate_ema(prices, slow)
        
        macd_line = [ema_fast[i] - ema_slow[i] if not np.isnan(ema_fast[i]) and not np.isnan(ema_slow[i]) 
                     else np.nan for i in range(len(prices))]
        
        # Remove NaN values for signal line calculation
        macd_clean = [x for x in macd_line if not np.isnan(x)]
        if len(macd_clean) < signal:
            signal_line = [np.nan] * len(prices)
        else:
            signal_ema = TechnicalIndicators.calculate_ema(macd_clean, signal)
            # Align signal line with original indices
            signal_line = [np.nan] * len(prices)
            nan_count = sum(1 for x in macd_line if np.isnan(x))
            signal_line[nan_count:] = signal_ema
        
        histogram = [macd_line[i] - signal_line[i] if not np.isnan(macd_line[i]) and not np.isnan(signal_line[i])
                     else np.nan for i in range(len(prices))]
        
        return MACD(
            macd_line=macd_line,
            signal_line=signal_line,
            histogram=histogram
        )
    
    @staticmethod
    def calculate_stochastic(klines: List[Kline], k_period: int = 14, d_period: int = 3) -> Stochastic:
        """Stochastic Oscillator."""
        if len(klines) < k_period:
            return Stochastic(
                k_percent=[np.nan] * len(klines),
                d_percent=[np.nan] * len(klines)
            )
        
        k_percent = []
        for i in range(len(klines)):
            if i < k_period - 1:
                k_percent.append(np.nan)
            else:
                period_highs = [klines[j].high for j in range(i - k_period + 1, i + 1)]
                period_lows = [klines[j].low for j in range(i - k_period + 1, i + 1)]
                
                highest_high = max(period_highs)
                lowest_low = min(period_lows)
                current_close = klines[i].close
                
                if highest_high == lowest_low:
                    k_percent.append(50.0)  # Avoid division by zero
                else:
                    k_val = ((current_close - lowest_low) / (highest_high - lowest_low)) * 100
                    k_percent.append(k_val)
        
        # Calculate %D as SMA of %K
        d_percent = TechnicalIndicators.calculate_sma(k_percent, d_period)
        
        return Stochastic(k_percent=k_percent, d_percent=d_percent)

    @staticmethod
    def calculate_adx(klines: List[Kline], period: int = 14) -> List[float]:
        """Average Directional Index (ADX)."""
        if len(klines) < period + 1:
            return [np.nan] * len(klines)

        highs = np.array([k.high for k in klines], dtype=float)
        lows = np.array([k.low for k in klines], dtype=float)
        closes = np.array([k.close for k in klines], dtype=float)

        plus_dm = np.zeros(len(klines))
        minus_dm = np.zeros(len(klines))
        tr = np.zeros(len(klines))

        for i in range(1, len(klines)):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            plus_dm[i] = up_move if up_move > down_move and up_move > 0 else 0.0
            minus_dm[i] = down_move if down_move > up_move and down_move > 0 else 0.0

            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i - 1])
            low_close = abs(lows[i] - closes[i - 1])
            tr[i] = max(high_low, high_close, low_close)

        adx = [np.nan] * len(klines)
        if len(klines) <= period:
            return adx

        tr_smooth = np.sum(tr[1:period + 1])
        plus_dm_smooth = np.sum(plus_dm[1:period + 1])
        minus_dm_smooth = np.sum(minus_dm[1:period + 1])

        def safe_div(num, denom):
            return (num / denom) * 100 if denom > 0 else 0.0

        plus_di = safe_div(plus_dm_smooth, tr_smooth)
        minus_di = safe_div(minus_dm_smooth, tr_smooth)
        dx = [np.nan] * len(klines)
        dx[period] = safe_div(abs(plus_di - minus_di), plus_di + minus_di)

        for i in range(period + 1, len(klines)):
            tr_smooth = tr_smooth - (tr_smooth / period) + tr[i]
            plus_dm_smooth = plus_dm_smooth - (plus_dm_smooth / period) + plus_dm[i]
            minus_dm_smooth = minus_dm_smooth - (minus_dm_smooth / period) + minus_dm[i]

            plus_di = safe_div(plus_dm_smooth, tr_smooth)
            minus_di = safe_div(minus_dm_smooth, tr_smooth)
            dx[i] = safe_div(abs(plus_di - minus_di), plus_di + minus_di)

        # ADX is the smoothed DX
        first_adx_index = period * 2
        if len(klines) > first_adx_index:
            initial_adx = np.nanmean(dx[period + 1:first_adx_index + 1])
            adx[first_adx_index] = initial_adx
            for i in range(first_adx_index + 1, len(klines)):
                prev = adx[i - 1] if not np.isnan(adx[i - 1]) else initial_adx
                adx[i] = ((prev * (period - 1)) + dx[i]) / period

        return adx

    @staticmethod
    def calculate_zscore(prices: List[float], window: int = 50) -> List[float]:
        """Z-score vs rolling mean."""
        if len(prices) < window:
            return [np.nan] * len(prices)

        zscores = [np.nan] * len(prices)
        for i in range(window - 1, len(prices)):
            window_prices = prices[i - window + 1:i + 1]
            mean = np.mean(window_prices)
            std = np.std(window_prices)
            zscores[i] = (prices[i] - mean) / std if std > 0 else 0.0
        return zscores

    @staticmethod
    def calculate_hurst_exponent(prices: List[float], max_lag: int = 20) -> float:
        """Estimate Hurst exponent using rescaled range."""
        if len(prices) < max_lag + 1:
            return np.nan

        lags = range(2, max_lag + 1)
        tau = []
        for lag in lags:
            diffs = np.subtract(prices[lag:], prices[:-lag])
            tau.append(np.std(diffs))

        tau = np.array(tau)
        if np.any(tau <= 0):
            return np.nan

        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        return float(poly[0] * 2.0)
    
    @staticmethod
    def get_signals(klines: List[Kline], config: Optional[IndicatorConfig] = None) -> List[str]:
        """Generate trading signals based on technical indicators."""
        if not config:
            config = IndicatorConfig()
        
        if len(klines) < 50:  # Need sufficient data
            return []
        
        signals = []
        prices = [k.close for k in klines]
        current_price = prices[-1]
        
        # RSI signals
        rsi = TechnicalIndicators.calculate_rsi(prices, config.rsi_period)
        if not np.isnan(rsi[-1]):
            if rsi[-1] < 30:
                signals.append("RSI_OVERSOLD")
            elif rsi[-1] > 70:
                signals.append("RSI_OVERBOUGHT")
        
        # Bollinger Bands signals
        bb = TechnicalIndicators.calculate_bollinger_bands(klines, config.bb_period, config.bb_std_dev)
        if not np.isnan(bb.bb_position[-1]):
            if bb.bb_position[-1] < 5:
                signals.append("BB_OVERSOLD")
            elif bb.bb_position[-1] > 95:
                signals.append("BB_OVERBOUGHT")
        
        # Moving Average signals
        sma_20 = TechnicalIndicators.calculate_sma(prices, 20)
        sma_50 = TechnicalIndicators.calculate_sma(prices, 50)
        
        if not np.isnan(sma_20[-1]) and not np.isnan(sma_50[-1]):
            if sma_20[-1] > sma_50[-1] and len(sma_20) > 1 and sma_20[-2] <= sma_50[-2]:
                signals.append("SMA_GOLDEN_CROSS")
            elif sma_20[-1] < sma_50[-1] and len(sma_20) > 1 and sma_20[-2] >= sma_50[-2]:
                signals.append("SMA_DEATH_CROSS")
        
        # Trend signals
        if not np.isnan(sma_20[-1]):
            if current_price > sma_20[-1] * 1.02:
                signals.append("STRONG_UPTREND")
            elif current_price < sma_20[-1] * 0.98:
                signals.append("STRONG_DOWNTREND")
        
        return signals
    
    @staticmethod
    def get_comprehensive_analysis(klines: List[Kline], symbol: str, config: Optional[IndicatorConfig] = None) -> 'TechnicalSummary':
        """Generate comprehensive technical analysis summary.
        
        Args:
            klines: List of candlestick data
            symbol: Trading symbol
            config: Indicator configuration
            
        Returns:
            TechnicalSummary with all indicators and analysis
        """
        from datetime import datetime
        from .types import TechnicalSummary
        
        if not config:
            config = IndicatorConfig()
        
        if len(klines) < 50:
            # Return empty summary for insufficient data
            return TechnicalSummary(
                symbol=symbol,
                timeframe="unknown",
                timestamp=datetime.now(),
                current_price=klines[-1].close if klines else 0,
                price_change_pct=0,
                sma_20=np.nan, sma_50=np.nan, ema_20=np.nan, rsi=np.nan,
                atr=np.nan, bollinger_position=np.nan,
                volume_sma_ratio=np.nan,
                signals=[], trend_score=0, momentum_score=0,
                volatility_percentile=np.nan,
                sma_200=np.nan, ema_50=np.nan, ema_200=np.nan,
                macd_line=np.nan, macd_signal=np.nan, macd_histogram=np.nan,
                bb_bandwidth_pct=np.nan,
                stoch_k=np.nan, stoch_d=np.nan,
                atr_pct=np.nan, atr_pct_percentile=np.nan,
                return_5_pct=np.nan, return_20_pct=np.nan,
                realized_vol_20_pct=np.nan,
                price_vs_sma20_pct=np.nan,
                price_vs_sma50_pct=np.nan,
                sma20_vs_sma50_pct=np.nan,
                ema_stack_alignment=np.nan,
                zscore_rolling=np.nan,
                trend_persistence_prob=np.nan,
                adx=np.nan,
                hurst_exponent=np.nan
            )
        
        prices = [k.close for k in klines]
        current_price = prices[-1]
        
        # Calculate all indicators
        rsi_values = TechnicalIndicators.calculate_rsi(prices, config.rsi_period)
        current_rsi = rsi_values[-1] if rsi_values and not np.isnan(rsi_values[-1]) else 50
        
        macd = TechnicalIndicators.calculate_macd(prices, config.macd_fast, config.macd_slow, config.macd_signal)
        macd_line = next((val for val in reversed(macd.macd_line) if not np.isnan(val)), np.nan)
        macd_signal = next((val for val in reversed(macd.signal_line) if not np.isnan(val)), np.nan)
        current_histogram = next((val for val in reversed(macd.histogram) if not np.isnan(val)), np.nan)
        
        atr_values = TechnicalIndicators.calculate_atr(klines, config.atr_period)
        current_atr = next((val for val in reversed(atr_values) if not np.isnan(val)), np.nan)
        
        bb = TechnicalIndicators.calculate_bollinger_bands(klines, config.bb_period, config.bb_std_dev)
        bb_position = next((val for val in reversed(bb.bb_position) if not np.isnan(val)), np.nan)
        bb_bandwidth = next((val for val in reversed(bb.bandwidth) if not np.isnan(val)), np.nan)
        
        sma_20 = TechnicalIndicators.calculate_sma(prices, 20)
        sma_50 = TechnicalIndicators.calculate_sma(prices, 50)
        sma_200 = TechnicalIndicators.calculate_sma(prices, 200)
        ema_20 = TechnicalIndicators.calculate_ema(prices, 20)
        ema_50 = TechnicalIndicators.calculate_ema(prices, 50)
        ema_200 = TechnicalIndicators.calculate_ema(prices, 200)

        current_sma_20 = sma_20[-1] if sma_20 and not np.isnan(sma_20[-1]) else np.nan
        current_sma_50 = sma_50[-1] if sma_50 and not np.isnan(sma_50[-1]) else np.nan
        current_sma_200 = sma_200[-1] if sma_200 and not np.isnan(sma_200[-1]) else np.nan
        current_ema_20 = ema_20[-1] if ema_20 and not np.isnan(ema_20[-1]) else np.nan
        current_ema_50 = ema_50[-1] if ema_50 and not np.isnan(ema_50[-1]) else np.nan
        current_ema_200 = ema_200[-1] if ema_200 and not np.isnan(ema_200[-1]) else np.nan

        stoch = TechnicalIndicators.calculate_stochastic(klines, config.stoch_k_period, config.stoch_d_period)
        stoch_k = stoch.k_percent[-1] if stoch.k_percent and not np.isnan(stoch.k_percent[-1]) else np.nan
        stoch_d = stoch.d_percent[-1] if stoch.d_percent and not np.isnan(stoch.d_percent[-1]) else np.nan
        
        # Trend diagnostics
        ema_stack_alignment = TechnicalIndicators._calculate_ema_stack_alignment(
            current_ema_20, current_ema_50, current_ema_200
        )
        zscore_rolling = TechnicalIndicators.calculate_zscore(prices, window=50)
        zscore_rolling_value = (
            zscore_rolling[-1] if zscore_rolling and not np.isnan(zscore_rolling[-1]) else np.nan
        )
        adx_values = TechnicalIndicators.calculate_adx(klines, period=14)
        adx_value = adx_values[-1] if adx_values and not np.isnan(adx_values[-1]) else np.nan
        hurst_exponent = TechnicalIndicators.calculate_hurst_exponent(prices, max_lag=20)
        trend_persistence_prob = TechnicalIndicators._calculate_trend_persistence_prob(ema_50, prices)
        
        # Retain legacy scores for compatibility
        trend_score = TechnicalIndicators._calculate_trend_score(current_price, current_sma_20, current_sma_50, current_histogram)
        momentum_score = TechnicalIndicators._calculate_momentum_score(
            current_rsi, current_histogram, bb_position, current_price
        )
        
        # Price change percentage
        price_change_pct = ((current_price - prices[-2]) / prices[-2] * 100) if len(prices) > 1 else np.nan
        return_5_pct = ((current_price - prices[-6]) / prices[-6] * 100) if len(prices) > 5 else np.nan
        return_20_pct = ((current_price - prices[-21]) / prices[-21] * 100) if len(prices) > 20 else np.nan

        # ATR percentage and percentile (history-based)
        atr_pct_values = [
            (atr_values[i] / prices[i] * 100) if not np.isnan(atr_values[i]) and prices[i] > 0 else np.nan
            for i in range(len(prices))
        ]
        atr_pct = next((val for val in reversed(atr_pct_values) if not np.isnan(val)), np.nan)
        valid_atr_pcts = [val for val in atr_pct_values if not np.isnan(val)]
        if valid_atr_pcts and not np.isnan(atr_pct):
            atr_pct_percentile = float(np.mean(np.array(valid_atr_pcts) <= atr_pct) * 100)
        else:
            atr_pct_percentile = np.nan

        # Realized volatility (non-annualized) over 20 periods
        if len(prices) > 20:
            returns = np.diff(prices[-21:]) / np.array(prices[-21:-1])
            realized_vol_20_pct = float(np.std(returns) * 100) if returns.size > 0 else np.nan
        else:
            realized_vol_20_pct = np.nan

        volatility_percentile = atr_pct_percentile
        
        # Get active signals
        signals = TechnicalIndicators.get_signals(klines, config)
        
        # Volume ratio (current vs 20-period SMA)
        volumes = [k.volume for k in klines]
        if len(volumes) >= config.volume_sma_period:
            volume_sma = float(np.mean(volumes[-config.volume_sma_period:]))
            volume_sma_ratio = (volumes[-1] / volume_sma) if volume_sma > 0 else np.nan
        else:
            volume_sma_ratio = np.nan

        price_vs_sma20_pct = (
            (current_price - current_sma_20) / current_sma_20 * 100
            if not np.isnan(current_sma_20) and current_sma_20 != 0
            else np.nan
        )
        price_vs_sma50_pct = (
            (current_price - current_sma_50) / current_sma_50 * 100
            if not np.isnan(current_sma_50) and current_sma_50 != 0
            else np.nan
        )
        sma20_vs_sma50_pct = (
            (current_sma_20 - current_sma_50) / current_sma_50 * 100
            if not np.isnan(current_sma_20) and not np.isnan(current_sma_50) and current_sma_50 != 0
            else np.nan
        )

        return TechnicalSummary(
            symbol=symbol,
            timeframe="unknown",  # Would be set by caller
            timestamp=datetime.now(),
            current_price=current_price,
            price_change_pct=price_change_pct,
            sma_20=current_sma_20,
            sma_50=current_sma_50,
            ema_20=current_ema_20,
            rsi=current_rsi,
            atr=current_atr,
            bollinger_position=bb_position,
            volume_sma_ratio=volume_sma_ratio,
            signals=signals,
            trend_score=trend_score,
            momentum_score=momentum_score,
            volatility_percentile=volatility_percentile,
            sma_200=current_sma_200,
            ema_50=current_ema_50,
            ema_200=current_ema_200,
            macd_line=macd_line,
            macd_signal=macd_signal,
            macd_histogram=current_histogram,
            bb_bandwidth_pct=bb_bandwidth,
            stoch_k=stoch_k,
            stoch_d=stoch_d,
            atr_pct=atr_pct,
            atr_pct_percentile=atr_pct_percentile,
            return_5_pct=return_5_pct,
            return_20_pct=return_20_pct,
            realized_vol_20_pct=realized_vol_20_pct,
            price_vs_sma20_pct=price_vs_sma20_pct,
            price_vs_sma50_pct=price_vs_sma50_pct,
            sma20_vs_sma50_pct=sma20_vs_sma50_pct,
            ema_stack_alignment=ema_stack_alignment,
            zscore_rolling=zscore_rolling_value,
            trend_persistence_prob=trend_persistence_prob,
            adx=adx_value,
            hurst_exponent=hurst_exponent
        )
    
    @staticmethod
    def _calculate_trend_score(price: float, sma_20: float, sma_50: float, histogram: float) -> float:
        """Calculate trend score from -100 to +100."""
        if any(np.isnan(val) for val in [price, sma_20, sma_50, histogram]) or price <= 0:
            return 0

        price_vs_sma20_pct = (price - sma_20) / sma_20 * 100 if sma_20 != 0 else 0
        price_vs_sma50_pct = (price - sma_50) / sma_50 * 100 if sma_50 != 0 else 0
        sma20_vs_sma50_pct = (sma_20 - sma_50) / sma_50 * 100 if sma_50 != 0 else 0
        histogram_pct = (histogram / price) * 100

        score = 0
        score += float(np.clip(price_vs_sma20_pct * 5, -30, 30))
        score += float(np.clip(price_vs_sma50_pct * 3, -25, 25))
        score += float(np.clip(sma20_vs_sma50_pct * 4, -25, 25))
        score += float(np.clip(histogram_pct * 10, -20, 20))

        return float(np.clip(score, -100, 100))
    
    @staticmethod
    def _calculate_momentum_score(rsi: float, histogram: float, bb_position: float, price: float) -> float:
        """Calculate momentum score from -100 to +100."""
        if any(np.isnan(val) for val in [rsi, histogram, bb_position, price]) or price <= 0:
            return 0

        histogram_pct = (histogram / price) * 100
        histogram_score = float(np.clip(histogram_pct * 6, -30, 30))
        rsi_score = float(np.clip((rsi - 50) * 1.6, -40, 40))
        bb_score = float(np.clip((bb_position - 50) * 0.6, -30, 30))

        score = rsi_score + histogram_score + bb_score
        return float(np.clip(score, -100, 100))

    @staticmethod
    def _calculate_ema_stack_alignment(ema_20: float, ema_50: float, ema_200: float) -> float:
        """EMA stack alignment: +1 bullish stack, -1 bearish stack, 0 mixed."""
        if any(np.isnan(val) for val in [ema_20, ema_50, ema_200]):
            return np.nan

        if ema_20 > ema_50 > ema_200:
            return 1.0
        if ema_20 < ema_50 < ema_200:
            return -1.0
        return 0.0

    @staticmethod
    def _calculate_trend_persistence_prob(ema_50: List[float], prices: List[float], window: int = 20) -> float:
        """Probability that recent returns align with EMA trend direction."""
        if len(prices) < window + 1 or len(ema_50) < window + 1:
            return np.nan

        ema_window = [val for val in ema_50[-(window + 1):] if not np.isnan(val)]
        if len(ema_window) < window + 1:
            return np.nan

        ema_slope = ema_window[-1] - ema_window[0]
        if ema_slope == 0:
            return 0.5

        returns = np.diff(prices[-(window + 1):])
        if returns.size == 0:
            return np.nan

        aligned = returns > 0 if ema_slope > 0 else returns < 0
        return float(np.mean(aligned))
    
    @staticmethod
    def get_compact_summary(technical_summary: 'TechnicalSummary') -> Dict[str, Any]:
        """Generate compact summary for LLM consumption.
        
        Args:
            technical_summary: TechnicalSummary object
            
        Returns:
            Dict with compact, LLM-optimized format
        """
        from .types import TechnicalSummary
        
        # Determine overall signal from industry metrics
        if (technical_summary.ema_stack_alignment == 1.0 and
                technical_summary.adx >= 20 and
                technical_summary.trend_persistence_prob >= 0.6):
            overall_signal = "bullish"
        elif (technical_summary.ema_stack_alignment == -1.0 and
                technical_summary.adx >= 20 and
                technical_summary.trend_persistence_prob >= 0.6):
            overall_signal = "bearish"
        else:
            overall_signal = "neutral"

        if np.isnan(technical_summary.adx) or np.isnan(technical_summary.trend_persistence_prob):
            signal_strength = 0.0
        else:
            signal_strength = min(technical_summary.adx * 2.0 * technical_summary.trend_persistence_prob, 100.0)
        
        # Risk level based on volatility
        if np.isnan(technical_summary.volatility_percentile):
            risk_level = "unknown"
        elif technical_summary.volatility_percentile > 70:
            risk_level = "high"
        elif technical_summary.volatility_percentile > 40:
            risk_level = "medium"
        else:
            risk_level = "low"
            
        # ATR percentage
        atr_pct = technical_summary.atr_pct if not np.isnan(technical_summary.atr_pct) else (
            (technical_summary.atr / technical_summary.current_price * 100)
            if technical_summary.current_price > 0 and not np.isnan(technical_summary.atr)
            else np.nan
        )
        
        if np.isnan(technical_summary.rsi):
            rsi_signal = "unknown"
        elif technical_summary.rsi > 70:
            rsi_signal = "overbought"
        elif technical_summary.rsi < 30:
            rsi_signal = "oversold"
        else:
            rsi_signal = "neutral"

        if np.isnan(technical_summary.sma_20) or np.isnan(technical_summary.sma_50):
            trend_direction = "unknown"
        elif technical_summary.sma_20 > technical_summary.sma_50:
            trend_direction = "bullish"
        elif technical_summary.sma_20 < technical_summary.sma_50:
            trend_direction = "bearish"
        else:
            trend_direction = "sideways"

        return {
            "overall_signal": overall_signal,
            "signal_strength": round(signal_strength, 1),
            "trend_score": round(technical_summary.trend_score, 1),
            "momentum_score": round(technical_summary.momentum_score, 1),
            "current_price": round(technical_summary.current_price, 6),
            "rsi": round(technical_summary.rsi, 1),
            "rsi_signal": rsi_signal,
            "trend_direction": trend_direction,
            "volatility_level": risk_level,
            "atr_pct": round(atr_pct, 2),
            "bb_position": round(technical_summary.bollinger_position, 1),
            "bb_bandwidth_pct": round(technical_summary.bb_bandwidth_pct, 2),
            "active_signals": technical_summary.signals,
            "strong_signals": len([s for s in technical_summary.signals if "STRONG" in s]),
            "volume_sma_ratio": round(technical_summary.volume_sma_ratio, 2),
            "return_5_pct": round(technical_summary.return_5_pct, 2),
            "return_20_pct": round(technical_summary.return_20_pct, 2),
            "realized_vol_20_pct": round(technical_summary.realized_vol_20_pct, 2),
            "atr_pct_percentile": round(technical_summary.atr_pct_percentile, 1),
            "macd_line": round(technical_summary.macd_line, 6),
            "macd_signal": round(technical_summary.macd_signal, 6),
            "macd_histogram": round(technical_summary.macd_histogram, 6),
            "stoch_k": round(technical_summary.stoch_k, 1),
            "stoch_d": round(technical_summary.stoch_d, 1),
            "sma_20": round(technical_summary.sma_20, 6),
            "sma_50": round(technical_summary.sma_50, 6),
            "sma_200": round(technical_summary.sma_200, 6),
            "ema_20": round(technical_summary.ema_20, 6),
            "ema_50": round(technical_summary.ema_50, 6),
            "ema_200": round(technical_summary.ema_200, 6),
            "price_vs_sma20_pct": round(technical_summary.price_vs_sma20_pct, 2),
            "price_vs_sma50_pct": round(technical_summary.price_vs_sma50_pct, 2),
            "sma20_vs_sma50_pct": round(technical_summary.sma20_vs_sma50_pct, 2),
            "ema_stack_alignment": technical_summary.ema_stack_alignment,
            "zscore_rolling": round(technical_summary.zscore_rolling, 3),
            "trend_persistence_prob": round(technical_summary.trend_persistence_prob, 3),
            "adx": round(technical_summary.adx, 2),
            "hurst_exponent": round(technical_summary.hurst_exponent, 3)
        }
