"""Volatility analysis and regime detection."""

import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .types import Kline, VolatilityMetrics, CompositeVolatilityMetrics, CVOLMetrics, ConvexityMetrics, AdvancedVolatilityMetrics


class VolatilityAnalysis:
    """Professional volatility analysis tools."""
    
    @staticmethod
    def calculate_realized_volatility(klines: List[Kline], period: int = 20) -> List[float]:
        """Calculate realized volatility using log returns."""
        if len(klines) < 2:
            return [np.nan] * len(klines)
        
        # Calculate log returns
        log_returns = []
        for i in range(1, len(klines)):
            if klines[i-1].close > 0 and klines[i].close > 0:
                log_return = np.log(klines[i].close / klines[i-1].close)
                log_returns.append(log_return)
            else:
                log_returns.append(0)
        
        # Calculate rolling volatility
        realized_vol = [np.nan]  # First candle has no return
        
        for i in range(1, len(klines)):
            if i < period:
                # Not enough data for full period
                available_returns = log_returns[:i]
                if len(available_returns) > 1:
                    vol = np.std(available_returns, ddof=1) * np.sqrt(365 * 24)  # Annualized for hourly data
                    realized_vol.append(vol)
                else:
                    realized_vol.append(np.nan)
            else:
                # Full period available - use correct indexing
                period_returns = log_returns[i-period:i]
                if len(period_returns) > 1:
                    vol = np.std(period_returns, ddof=1) * np.sqrt(365 * 24)  # Annualized
                    realized_vol.append(vol)
                else:
                    realized_vol.append(np.nan)
        
        return realized_vol
    
    @staticmethod
    def calculate_garman_klass_volatility(klines: List[Kline]) -> List[float]:
        """Calculate Garman-Klass volatility estimator using OHLC data."""
        if len(klines) < 1:
            return []
        
        gk_values = []
        
        for kline in klines:
            if kline.open > 0 and kline.high > 0 and kline.low > 0 and kline.close > 0:
                # Garman-Klass estimator
                log_hl = np.log(kline.high / kline.low)
                log_co = np.log(kline.close / kline.open)
                
                gk = 0.5 * (log_hl ** 2) - (2 * np.log(2) - 1) * (log_co ** 2)
                gk_values.append(gk)
            else:
                gk_values.append(np.nan)
        
        # Convert to annualized volatility
        annualized_gk = [np.sqrt(gk * 365 * 24) if not np.isnan(gk) else np.nan for gk in gk_values]
        return annualized_gk
    
    @staticmethod
    def calculate_volatility_cone(klines: List[Kline]) -> Dict[str, float]:
        """Calculate volatility cone for different time periods."""
        if len(klines) < 30:
            return {}
        
        # Calculate realized volatility for different periods
        periods = [5, 10, 20, 30, 60]
        cone = {}
        
        for period in periods:
            if len(klines) >= period:
                realized_vols = []
                
                # Calculate rolling volatility for the period
                for i in range(period, len(klines)):
                    period_klines = klines[i-period:i]
                    log_returns = []
                    
                    for j in range(1, len(period_klines)):
                        if period_klines[j-1].close > 0 and period_klines[j].close > 0:
                            log_return = np.log(period_klines[j].close / period_klines[j-1].close)
                            log_returns.append(log_return)
                    
                    if len(log_returns) > 1:
                        vol = np.std(log_returns, ddof=1) * np.sqrt(365 * 24)
                        realized_vols.append(vol)
                
                if realized_vols:
                    cone[f"{period}d"] = {
                        "min": min(realized_vols),
                        "max": max(realized_vols),
                        "mean": np.mean(realized_vols),
                        "current": realized_vols[-1] if realized_vols else 0,
                        "percentile": len([v for v in realized_vols if v < realized_vols[-1]]) / len(realized_vols) * 100 if realized_vols else 0
                    }
        
        return cone
    
    @staticmethod
    def detect_volatility_regime(klines: List[Kline], lookback_period: int = 252) -> str:
        """Detect current volatility regime."""
        if len(klines) < 30:
            return "unknown"
        
        # Calculate current realized volatility (20-day)
        current_vol = VolatilityAnalysis.calculate_realized_volatility(klines[-21:], 20)
        if not current_vol or np.isnan(current_vol[-1]):
            return "unknown"
        
        current_realized_vol = current_vol[-1]
        
        # Calculate historical volatility distribution
        all_vol_values = []
        period = 20
        
        for i in range(period, min(len(klines), lookback_period + period)):
            period_klines = klines[i-period:i]
            log_returns = []
            
            for j in range(1, len(period_klines)):
                if period_klines[j-1].close > 0 and period_klines[j].close > 0:
                    log_return = np.log(period_klines[j].close / period_klines[j-1].close)
                    log_returns.append(log_return)
            
            if len(log_returns) > 1:
                vol = np.std(log_returns, ddof=1) * np.sqrt(365 * 24)
                all_vol_values.append(vol)
        
        if len(all_vol_values) < 10:
            return "unknown"
        
        # Calculate percentiles
        vol_25th = np.percentile(all_vol_values, 25)
        vol_75th = np.percentile(all_vol_values, 75)
        vol_90th = np.percentile(all_vol_values, 90)
        vol_10th = np.percentile(all_vol_values, 10)
        
        # Classify regime
        if current_realized_vol > vol_90th:
            return "extreme"
        elif current_realized_vol > vol_75th:
            return "high"
        elif current_realized_vol < vol_10th:
            return "low"
        elif current_realized_vol < vol_25th:
            return "low_normal"
        else:
            return "normal"
    
    @staticmethod
    def analyze_volatility_surface(base_coin: str, underlying_price: float, 
                                  options_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze volatility surface structure for opportunities."""
        if not options_data:
            return {"error": "No options data available"}
        
        # Group by expiry
        expiry_groups = {}
        for option in options_data:
            expiry = option.get('expiry_date', 'unknown')
            if expiry not in expiry_groups:
                expiry_groups[expiry] = []
            expiry_groups[expiry].append(option)
        
        surface_analysis = {
            "base_coin": base_coin,
            "underlying_price": underlying_price,
            "analysis_timestamp": datetime.now().isoformat(),
            "expiries_analyzed": len(expiry_groups),
            "opportunities": []
        }
        
        for expiry, expiry_options in expiry_groups.items():
            if len(expiry_options) < 3:  # Need minimum options for analysis
                continue
            
            # Separate calls and puts
            calls = [opt for opt in expiry_options if opt['symbol'].endswith('-C')]
            puts = [opt for opt in expiry_options if opt['symbol'].endswith('-P')]
            
            # Analyze skew for this expiry
            skew_analysis = VolatilityAnalysis._analyze_vol_skew(calls, puts, underlying_price)
            
            if skew_analysis:
                surface_analysis["opportunities"].extend(skew_analysis.get("opportunities", []))
        
        return surface_analysis
    
    @staticmethod
    def _analyze_vol_skew(calls: List[Dict], puts: List[Dict], underlying_price: float) -> Optional[Dict]:
        """Analyze volatility skew for a single expiry."""
        if len(calls) < 3 and len(puts) < 3:
            return None
        
        # Calculate moneyness and IV for options
        call_data = []
        put_data = []
        
        for call in calls:
            strike = float(call.get('strike', 0))
            iv = float(call.get('mark_iv', 0))
            if strike > 0 and iv > 0:
                moneyness = strike / underlying_price
                call_data.append((moneyness, iv))
        
        for put in puts:
            strike = float(put.get('strike', 0))
            iv = float(put.get('mark_iv', 0))
            if strike > 0 and iv > 0:
                moneyness = strike / underlying_price
                put_data.append((moneyness, iv))
        
        opportunities = []
        
        # Check for put-call skew
        if call_data and put_data:
            # Find ATM options
            atm_calls = [iv for moneyness, iv in call_data if 0.95 <= moneyness <= 1.05]
            atm_puts = [iv for moneyness, iv in put_data if 0.95 <= moneyness <= 1.05]
            
            if atm_calls and atm_puts:
                avg_call_iv = np.mean(atm_calls)
                avg_put_iv = np.mean(atm_puts)
                skew = avg_put_iv - avg_call_iv
                
                if abs(skew) > 0.05:  # 5% skew threshold
                    opportunities.append({
                        "type": "volatility_skew",
                        "skew_value": skew,
                        "direction": "put_favored" if skew > 0 else "call_favored",
                        "suggestion": f"Consider {'selling puts' if skew > 0 else 'selling calls'} - elevated IV",
                        "confidence": "high" if abs(skew) > 0.1 else "medium"
                    })
        
        return {"opportunities": opportunities} if opportunities else None
    
    @staticmethod
    def calculate_comprehensive_metrics(klines: List[Kline]) -> VolatilityMetrics:
        """Calculate comprehensive volatility metrics."""
        if len(klines) < 30:
            return VolatilityMetrics(
                realized_vol=[],
                historical_vol_20d=0,
                historical_vol_30d=0,
                volatility_cone={},
                regime="unknown",
                garman_klass_vol=[],
                vol_percentile=0
            )
        
        # Calculate various volatility measures
        realized_vol = VolatilityAnalysis.calculate_realized_volatility(klines, 20)
        garman_klass_vol = VolatilityAnalysis.calculate_garman_klass_volatility(klines)
        volatility_cone = VolatilityAnalysis.calculate_volatility_cone(klines)
        regime = VolatilityAnalysis.detect_volatility_regime(klines)
        
        # Calculate specific period volatilities
        historical_vol_20d = realized_vol[-1] if realized_vol and not np.isnan(realized_vol[-1]) else 0
        
        if len(klines) >= 31:
            vol_30d = VolatilityAnalysis.calculate_realized_volatility(klines[-31:], 30)
            historical_vol_30d = vol_30d[-1] if vol_30d and not np.isnan(vol_30d[-1]) else 0
        else:
            historical_vol_30d = historical_vol_20d
        
        # Calculate volatility percentile
        all_realized_vol = [v for v in realized_vol if not np.isnan(v)]
        if all_realized_vol and historical_vol_20d > 0:
            vol_percentile = len([v for v in all_realized_vol if v < historical_vol_20d]) / len(all_realized_vol) * 100
        else:
            vol_percentile = 0
        
        return VolatilityMetrics(
            realized_vol=realized_vol,
            historical_vol_20d=historical_vol_20d,
            historical_vol_30d=historical_vol_30d,
            volatility_cone=volatility_cone,
            regime=regime,
            garman_klass_vol=garman_klass_vol,
            vol_percentile=vol_percentile
        )
    
    @staticmethod
    def get_vol_trigger_levels(klines: List[Kline], current_vol: float) -> List[float]:
        """Calculate price levels that could trigger volatility regime changes."""
        if len(klines) < 20:
            return []
        
        current_price = klines[-1].close
        
        # Calculate typical price moves for different volatility regimes
        trigger_levels = []
        
        # Daily volatility
        daily_vol = current_vol / np.sqrt(365)
        
        # 1-sigma, 2-sigma moves
        for sigma in [1, 2]:
            move = current_price * daily_vol * sigma
            trigger_levels.extend([
                current_price + move,  # Upside trigger
                current_price - move   # Downside trigger
            ])
        
        # ATR-based triggers
        if len(klines) >= 14:
            atr_values = []
            for i in range(1, min(15, len(klines))):
                high_low = klines[i].high - klines[i].low
                high_close_prev = abs(klines[i].high - klines[i-1].close)
                low_close_prev = abs(klines[i].low - klines[i-1].close)
                
                true_range = max(high_low, high_close_prev, low_close_prev)
                atr_values.append(true_range)
            
            if atr_values:
                avg_atr = np.mean(atr_values)
                trigger_levels.extend([
                    current_price + (2 * avg_atr),
                    current_price - (2 * avg_atr)
                ])
        
        return sorted(list(set(trigger_levels)))  # Remove duplicates and sort
    
    @staticmethod
    def calculate_composite_volatility(klines: List[Kline], lookback_periods: List[int] = None) -> CompositeVolatilityMetrics:
        """
        Calculate Composite Volatility - a weighted combination of different volatility measures.
        
        Composite Volatility combines:
        - Realized volatility (40% weight)
        - Garman-Klass volatility (30% weight) 
        - ATR-based volatility (20% weight)
        - Short-term volatility spike detection (10% weight)
        
        Args:
            klines: Price data
            lookback_periods: Different periods for volatility calculation
            
        Returns:
            CompositeVolatilityMetrics with composite volatility analysis
        """
        if len(klines) < 20:
            return CompositeVolatilityMetrics(
                composite_vol_value=0,
                composite_vol_percentile=0,
                composite_vol_regime="unknown",
                components={}
            )
        
        if lookback_periods is None:
            lookback_periods = [10, 20, 30]
        
        # Component 1: Realized Volatility (40% weight)
        realized_vol_20 = VolatilityAnalysis.calculate_realized_volatility(klines, 20)
        current_realized = realized_vol_20[-1] if realized_vol_20 and not np.isnan(realized_vol_20[-1]) else 0
        
        # Component 2: Garman-Klass Volatility (30% weight)
        gk_vol = VolatilityAnalysis.calculate_garman_klass_volatility(klines)
        current_gk = gk_vol[-1] if gk_vol and not np.isnan(gk_vol[-1]) else 0
        
        # Component 3: ATR-based volatility (20% weight)
        from .technical import TechnicalIndicators
        atr_values = TechnicalIndicators.calculate_atr(klines, 14)
        current_atr = 0
        if atr_values:
            for atr in reversed(atr_values):
                if not np.isnan(atr):
                    current_atr = atr
                    break
        
        current_price = klines[-1].close
        atr_vol = (current_atr / current_price) * np.sqrt(365) * 100 if current_price > 0 else 0
        
        # Component 4: Short-term volatility spike (10% weight)
        if len(klines) >= 5:
            recent_returns = []
            for i in range(1, min(6, len(klines))):
                if klines[-i-1].close > 0:
                    ret = np.log(klines[-i].close / klines[-i-1].close)
                    recent_returns.append(ret)
            
            spike_vol = np.std(recent_returns) * np.sqrt(365) * 100 if recent_returns else 0
        else:
            spike_vol = 0
        
        # Calculate Composite Volatility as weighted average
        components = {
            "realized_volatility": current_realized,
            "garman_klass_volatility": current_gk,
            "atr_volatility": atr_vol,
            "spike_volatility": spike_vol
        }
        
        composite_vol_value = (
            current_realized * 0.4 +
            current_gk * 0.3 +
            atr_vol * 0.2 +
            spike_vol * 0.1
        )
        
        # Calculate Composite Volatility percentile using historical data
        historical_composite_vol = []
        min_window = max(lookback_periods) + 10
        
        if len(klines) > min_window:
            for i in range(min_window, len(klines)):
                hist_klines = klines[i-min_window:i]
                
                # Calculate historical components
                hist_realized = VolatilityAnalysis.calculate_realized_volatility(hist_klines, 20)
                hist_gk = VolatilityAnalysis.calculate_garman_klass_volatility(hist_klines)
                hist_atr = TechnicalIndicators.calculate_atr(hist_klines, 14)
                
                hist_realized_val = hist_realized[-1] if hist_realized and not np.isnan(hist_realized[-1]) else 0
                hist_gk_val = hist_gk[-1] if hist_gk and not np.isnan(hist_gk[-1]) else 0
                
                hist_atr_val = 0
                if hist_atr:
                    for atr in reversed(hist_atr):
                        if not np.isnan(atr):
                            hist_atr_val = atr
                            break
                
                hist_price = hist_klines[-1].close
                hist_atr_vol = (hist_atr_val / hist_price) * np.sqrt(365) * 100 if hist_price > 0 else 0
                
                # Calculate recent spike
                if len(hist_klines) >= 5:
                    hist_returns = []
                    for j in range(1, 6):
                        if hist_klines[-j-1].close > 0:
                            ret = np.log(hist_klines[-j].close / hist_klines[-j-1].close)
                            hist_returns.append(ret)
                    hist_spike_vol = np.std(hist_returns) * np.sqrt(365) * 100 if hist_returns else 0
                else:
                    hist_spike_vol = 0
                
                hist_composite_vol = (
                    hist_realized_val * 0.4 +
                    hist_gk_val * 0.3 +
                    hist_atr_vol * 0.2 +
                    hist_spike_vol * 0.1
                )
                
                historical_composite_vol.append(hist_composite_vol)
        
        # Calculate percentile
        if historical_composite_vol:
            composite_vol_percentile = len([v for v in historical_composite_vol if v < composite_vol_value]) / len(historical_composite_vol) * 100
        else:
            composite_vol_percentile = 50  # Default to median if no historical data
        
        # Determine Composite Volatility regime
        if composite_vol_percentile > 90:
            composite_vol_regime = "extreme"
        elif composite_vol_percentile > 75:
            composite_vol_regime = "high"
        elif composite_vol_percentile < 10:
            composite_vol_regime = "low"
        elif composite_vol_percentile < 25:
            composite_vol_regime = "low_normal"
        else:
            composite_vol_regime = "normal"
        
        return CompositeVolatilityMetrics(
            composite_vol_value=composite_vol_value,
            composite_vol_percentile=composite_vol_percentile,
            composite_vol_regime=composite_vol_regime,
            components=components
        )
    
    @staticmethod
    def calculate_convexity(klines: List[Kline], period: int = 20) -> ConvexityMetrics:
        """
        Calculate price convexity - the rate of change of price momentum.
        
        Convexity measures the acceleration in price movements, which is crucial
        for gamma exposure analysis in options trading.
        
        Args:
            klines: Price data
            period: Period for convexity calculation
            
        Returns:
            ConvexityMetrics with convexity analysis
        """
        if len(klines) < period + 2:
            return ConvexityMetrics(
                convexity_value=0,
                convexity_trend="unknown",
                convexity_regime="unknown",
                price_acceleration=0
            )
        
        prices = [k.close for k in klines]
        
        # Calculate first and second derivatives of price
        first_derivatives = np.gradient(prices)
        second_derivatives = np.gradient(first_derivatives)
        
        # Current convexity (second derivative normalized by price)
        current_price = prices[-1]
        current_convexity = second_derivatives[-1] / current_price if current_price != 0 else 0
        
        # Calculate recent convexity trend
        recent_convexity = second_derivatives[-period:] / np.array(prices[-period:])
        recent_convexity = recent_convexity[~np.isnan(recent_convexity)]
        
        if len(recent_convexity) > 5:
            # Linear regression to determine trend
            x = np.arange(len(recent_convexity))
            slope = np.polyfit(x, recent_convexity, 1)[0]
            
            if slope > 0.001:
                convexity_trend = "increasing"
            elif slope < -0.001:
                convexity_trend = "decreasing"
            else:
                convexity_trend = "stable"
        else:
            convexity_trend = "unknown"
        
        # Calculate historical convexity distribution for regime classification
        if len(prices) > period * 2:
            historical_convexity = []
            for i in range(period, len(prices) - period):
                window_prices = prices[i:i+period]
                window_first_deriv = np.gradient(window_prices)
                window_second_deriv = np.gradient(window_first_deriv)
                
                if window_prices[-1] != 0:
                    hist_convex = window_second_deriv[-1] / window_prices[-1]
                    historical_convexity.append(hist_convex)
            
            if historical_convexity:
                convex_75th = np.percentile(historical_convexity, 75)
                convex_25th = np.percentile(historical_convexity, 25)
                
                if current_convexity > convex_75th:
                    convexity_regime = "high"
                elif current_convexity < convex_25th:
                    convexity_regime = "low"
                else:
                    convexity_regime = "normal"
            else:
                convexity_regime = "normal"
        else:
            convexity_regime = "normal"
        
        return ConvexityMetrics(
            convexity_value=current_convexity,
            convexity_trend=convexity_trend,
            convexity_regime=convexity_regime,
            price_acceleration=second_derivatives[-1]
        )
    
    @staticmethod
    def calculate_cvol(options_data: List[Dict[str, Any]], underlying_price: float) -> CVOLMetrics:
        """
        Calculate CVOL (Composite Implied Volatility) across all strikes per expiry/asset.
        
        Args:
            options_data: List of options with IV, strike, expiry, volume, OI data
            underlying_price: Current underlying asset price
            
        Returns:
            CVOLMetrics with implied volatility analysis across all strikes
        """
        if not options_data or not underlying_price:
            return CVOLMetrics(
                cvol_by_expiry={},
                cvol_overall=0,
                cvol_by_moneyness={},
                cvol_skew={},
                total_open_interest=0,
                volume_weighted_iv=0
            )
        
        # Group by expiry
        expiry_groups = {}
        for option in options_data:
            try:
                expiry = option.get('expiry_date', 'unknown')
                if expiry not in expiry_groups:
                    expiry_groups[expiry] = []
                expiry_groups[expiry].append(option)
            except (KeyError, TypeError):
                continue
        
        # Calculate CVOL by expiry
        cvol_by_expiry = {}
        all_ivs = []
        all_volumes = []
        all_ois = []
        
        for expiry, expiry_options in expiry_groups.items():
            if not expiry_options:
                continue
                
            expiry_ivs = []
            expiry_volumes = []
            
            for option in expiry_options:
                try:
                    iv = float(option.get('mark_iv', 0)) * 100  # Convert to percentage
                    volume = float(option.get('volume_24h', 0))
                    oi = float(option.get('open_interest', 0))
                    
                    if iv > 0:  # Only include options with valid IV
                        expiry_ivs.append(iv)
                        expiry_volumes.append(volume)
                        all_ivs.append(iv)
                        all_volumes.append(volume)
                        all_ois.append(oi)
                except (ValueError, TypeError):
                    continue
            
            if expiry_ivs:
                # Calculate volume-weighted average IV for this expiry
                if sum(expiry_volumes) > 0:
                    weighted_iv = sum(iv * vol for iv, vol in zip(expiry_ivs, expiry_volumes)) / sum(expiry_volumes)
                else:
                    weighted_iv = np.mean(expiry_ivs)
                
                cvol_by_expiry[expiry] = weighted_iv
        
        # Calculate overall CVOL (volume-weighted across all options)
        if all_ivs and sum(all_volumes) > 0:
            cvol_overall = sum(iv * vol for iv, vol in zip(all_ivs, all_volumes)) / sum(all_volumes)
        elif all_ivs:
            cvol_overall = np.mean(all_ivs)
        else:
            cvol_overall = 0
        
        # Calculate CVOL by moneyness buckets
        cvol_by_moneyness = {}
        moneyness_buckets = {
            "deep_otm": (0, 0.8),
            "otm": (0.8, 0.95),
            "atm": (0.95, 1.05),
            "itm": (1.05, 1.2),
            "deep_itm": (1.2, float('inf'))
        }
        
        for bucket_name, (low, high) in moneyness_buckets.items():
            bucket_ivs = []
            bucket_volumes = []
            
            for option in options_data:
                try:
                    strike = float(option.get('strike', 0))
                    iv = float(option.get('mark_iv', 0)) * 100
                    volume = float(option.get('volume_24h', 0))
                    
                    if strike > 0 and iv > 0:
                        moneyness = strike / underlying_price
                        if low <= moneyness < high:
                            bucket_ivs.append(iv)
                            bucket_volumes.append(volume)
                except (ValueError, TypeError):
                    continue
            
            if bucket_ivs:
                if sum(bucket_volumes) > 0:
                    bucket_cvol = sum(iv * vol for iv, vol in zip(bucket_ivs, bucket_volumes)) / sum(bucket_volumes)
                else:
                    bucket_cvol = np.mean(bucket_ivs)
                cvol_by_moneyness[bucket_name] = bucket_cvol
        
        # Calculate put-call skew
        cvol_skew = {}
        try:
            calls = [opt for opt in options_data if opt.get('symbol', '').endswith('-C')]
            puts = [opt for opt in options_data if opt.get('symbol', '').endswith('-P')]
            
            atm_call_ivs = []
            atm_put_ivs = []
            
            # Find ATM options (within 5% of underlying)
            for call in calls:
                try:
                    strike = float(call.get('strike', 0))
                    iv = float(call.get('mark_iv', 0)) * 100
                    if strike > 0 and iv > 0:
                        moneyness = abs(strike - underlying_price) / underlying_price
                        if moneyness <= 0.05:
                            atm_call_ivs.append(iv)
                except (ValueError, TypeError):
                    continue
            
            for put in puts:
                try:
                    strike = float(put.get('strike', 0))
                    iv = float(put.get('mark_iv', 0)) * 100
                    if strike > 0 and iv > 0:
                        moneyness = abs(strike - underlying_price) / underlying_price
                        if moneyness <= 0.05:
                            atm_put_ivs.append(iv)
                except (ValueError, TypeError):
                    continue
            
            if atm_call_ivs and atm_put_ivs:
                avg_call_iv = np.mean(atm_call_ivs)
                avg_put_iv = np.mean(atm_put_ivs)
                cvol_skew = {
                    "put_call_skew": avg_put_iv - avg_call_iv,
                    "atm_call_iv": avg_call_iv,
                    "atm_put_iv": avg_put_iv
                }
        except Exception:
            pass
        
        # Calculate totals
        total_open_interest = sum(all_ois)
        
        # Volume-weighted IV
        if all_ivs and sum(all_volumes) > 0:
            volume_weighted_iv = sum(iv * vol for iv, vol in zip(all_ivs, all_volumes)) / sum(all_volumes)
        else:
            volume_weighted_iv = cvol_overall
        
        return CVOLMetrics(
            cvol_by_expiry=cvol_by_expiry,
            cvol_overall=cvol_overall,
            cvol_by_moneyness=cvol_by_moneyness,
            cvol_skew=cvol_skew,
            total_open_interest=total_open_interest,
            volume_weighted_iv=volume_weighted_iv
        )
    
    @staticmethod
    def calculate_composite_atm_ratio(composite_vol_metrics: CompositeVolatilityMetrics, options_data: List[Dict[str, Any]] = None, 
                                     underlying_price: float = None) -> float:
        """
        Calculate the ratio of Composite Volatility to ATM strike volatility.
        
        This ratio helps identify volatility premium/discount relative to implied volatility
        at the money strikes.
        
        Args:
            composite_vol_metrics: Composite Volatility metrics 
            options_data: Options market data with IV information
            underlying_price: Current underlying asset price
            
        Returns:
            Composite Vol/ATM volatility ratio
        """
        if composite_vol_metrics.composite_vol_value <= 0:
            return 0
        
        # If no options data provided, return Composite Vol as baseline
        if not options_data or not underlying_price:
            return composite_vol_metrics.composite_vol_value
        
        # Find ATM options and calculate average IV
        atm_ivs = []
        
        for option in options_data:
            try:
                strike = float(option.get('strike', 0))
                iv = float(option.get('mark_iv', 0)) * 100  # Convert to percentage
                
                # Consider options within 5% of ATM as near-ATM
                moneyness = abs(strike - underlying_price) / underlying_price
                
                if moneyness <= 0.05 and iv > 0:
                    atm_ivs.append(iv)
            except (ValueError, TypeError):
                continue
        
        if atm_ivs:
            avg_atm_iv = np.mean(atm_ivs)
            ratio = composite_vol_metrics.composite_vol_value / avg_atm_iv
            return ratio
        else:
            # No ATM options found, return Composite Vol as fallback
            return composite_vol_metrics.composite_vol_value
    
    @staticmethod
    def calculate_advanced_volatility_metrics(klines: List[Kline], options_data: List[Dict[str, Any]] = None,
                                            underlying_price: float = None) -> AdvancedVolatilityMetrics:
        """
        Calculate comprehensive advanced volatility metrics.
        
        Args:
            klines: Price data
            options_data: Optional options market data for IV analysis
            underlying_price: Current underlying price
            
        Returns:
            AdvancedVolatilityMetrics with all advanced volatility calculations
        """
        # Calculate Composite Volatility metrics
        composite_vol_metrics = VolatilityAnalysis.calculate_composite_volatility(klines)
        
        # Calculate CVOL metrics (Implied Volatility across all strikes)
        if options_data and underlying_price:
            cvol_metrics = VolatilityAnalysis.calculate_cvol(options_data, underlying_price)
        else:
            cvol_metrics = CVOLMetrics(
                cvol_by_expiry={},
                cvol_overall=0,
                cvol_by_moneyness={},
                cvol_skew={},
                total_open_interest=0,
                volume_weighted_iv=0
            )
        
        # Calculate convexity metrics  
        convexity_metrics = VolatilityAnalysis.calculate_convexity(klines)
        
        # Calculate Composite Vol/ATM ratio
        composite_atm_ratio = VolatilityAnalysis.calculate_composite_atm_ratio(
            composite_vol_metrics, options_data, underlying_price
        )
        
        # Calculate volatility skew (basic implementation)
        volatility_skew = {}
        if options_data and underlying_price:
            try:
                calls = [opt for opt in options_data if opt.get('symbol', '').endswith('-C')]
                puts = [opt for opt in options_data if opt.get('symbol', '').endswith('-P')]
                
                # Calculate call/put IV difference for ATM options
                atm_call_ivs = []
                atm_put_ivs = []
                
                for call in calls:
                    strike = float(call.get('strike', 0))
                    iv = float(call.get('mark_iv', 0)) * 100
                    moneyness = abs(strike - underlying_price) / underlying_price
                    if moneyness <= 0.05 and iv > 0:
                        atm_call_ivs.append(iv)
                
                for put in puts:
                    strike = float(put.get('strike', 0))
                    iv = float(put.get('mark_iv', 0)) * 100
                    moneyness = abs(strike - underlying_price) / underlying_price
                    if moneyness <= 0.05 and iv > 0:
                        atm_put_ivs.append(iv)
                
                if atm_call_ivs and atm_put_ivs:
                    avg_call_iv = np.mean(atm_call_ivs)
                    avg_put_iv = np.mean(atm_put_ivs)
                    volatility_skew = {
                        "put_call_skew": avg_put_iv - avg_call_iv,
                        "atm_call_iv": avg_call_iv,
                        "atm_put_iv": avg_put_iv
                    }
            except (ValueError, TypeError, KeyError):
                pass
        
        # Calculate basic term structure (different volatility periods)
        term_structure = {}
        for period in [10, 20, 30, 60]:
            if len(klines) >= period:
                period_vol = VolatilityAnalysis.calculate_realized_volatility(klines, period)
                if period_vol and not np.isnan(period_vol[-1]):
                    term_structure[f"{period}d"] = period_vol[-1]
        
        return AdvancedVolatilityMetrics(
            composite_vol_metrics=composite_vol_metrics,
            cvol_metrics=cvol_metrics,
            convexity_metrics=convexity_metrics,
            composite_atm_ratio=composite_atm_ratio,
            volatility_skew=volatility_skew,
            term_structure=term_structure
        )