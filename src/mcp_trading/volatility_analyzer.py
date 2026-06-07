"""Asset-specific volatility analysis using real Bybit data."""

import logging
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger('strategy_logger')

@dataclass
class VolatilityProfile:
    """Comprehensive volatility profile for an asset."""
    asset: str
    realized_vol_7d: float      # 7-day realized volatility (annualized)
    realized_vol_30d: float     # 30-day realized volatility (annualized)  
    implied_vol_avg: float      # Average implied volatility from options
    risk_reversal_25d: float    # 25-delta risk reversal (call IV - put IV)
    skew_10d: float             # 10-delta skew (put IV - call IV)
    vol_of_vol: float           # Cross-sectional IV dispersion
    realized_implied_spread: float  # Implied - realized (30d) spread
    vol_risk_premium: float     # (Implied / Realized) - 1
    vol_regime: str             # LOW, MEDIUM, HIGH, EXTREME
    vol_percentile: float       # Current vol vs historical (0-100)
    optimal_bands: List[float]  # Recommended delta bands for this asset
    hedge_frequency_modifier: float  # Multiplier for base hedge frequencies
    rationale: str              # Explanation of band selection

@dataclass 
class AssetVolatilityConfig:
    """Configuration for asset-specific volatility analysis."""
    lookback_days: int = 30
    percentile_window_days: int = 365
    low_vol_threshold: float = 0.4      # 40% annual
    medium_vol_threshold: float = 0.8   # 80% annual  
    high_vol_threshold: float = 1.5     # 150% annual
    extreme_vol_threshold: float = 2.5  # 250% annual

class VolatilityAnalyzer:
    """Analyzes asset-specific volatility and recommends trading parameters."""
    
    def __init__(self, api_adapter, config: AssetVolatilityConfig = None):
        self.api = api_adapter
        self.config = config or AssetVolatilityConfig()
        
        # Asset-specific volatility cache
        self.vol_cache: Dict[str, VolatilityProfile] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        self.cache_ttl_minutes = 15  # Refresh every 15 minutes
    
    async def get_volatility_profile(self, asset: str, force_refresh: bool = False) -> VolatilityProfile:
        """Get comprehensive volatility profile for an asset."""
        
        # Check cache
        now = datetime.now()
        if (not force_refresh and 
            asset in self.vol_cache and 
            asset in self.cache_timestamps and
            (now - self.cache_timestamps[asset]).total_seconds() < self.cache_ttl_minutes * 60):
            return self.vol_cache[asset]
        
        logger.info(f"🔍 Analyzing volatility for {asset}...")
        
        # Fetch multiple data sources
        realized_vol_7d = await self._calculate_realized_volatility(asset, days=7)
        realized_vol_30d = await self._calculate_realized_volatility(asset, days=30)
        option_prices = await self._get_option_prices(asset)
        implied_vol_avg = self._calculate_average_implied_volatility(option_prices)
        
        # Get current underlying price for proper ATM calculation
        underlying_price = 50000  # Default BTC price
        if option_prices and hasattr(option_prices[0], 'underlying_price'):
            underlying_price = option_prices[0].underlying_price
        
        surface_metrics = self._calculate_vol_surface_metrics(option_prices, realized_vol_30d, underlying_price)
        
        # Determine volatility regime
        current_vol = max(realized_vol_7d, realized_vol_30d)  # Use higher of recent vols
        vol_regime = self._classify_vol_regime(current_vol)
        
        # Calculate historical percentile
        vol_percentile = await self._calculate_vol_percentile(asset, current_vol)
        
        # Generate optimal bands for this asset
        optimal_bands = self._generate_asset_bands(asset, current_vol, vol_regime, vol_percentile)
        
        # Calculate hedge frequency modifier
        hedge_freq_modifier = self._calculate_hedge_frequency_modifier(current_vol, vol_regime)
        
        # Generate rationale
        rationale = self._generate_volatility_rationale(
            asset, current_vol, vol_regime, vol_percentile, realized_vol_7d, realized_vol_30d
        )
        
        profile = VolatilityProfile(
            asset=asset,
            realized_vol_7d=realized_vol_7d,
            realized_vol_30d=realized_vol_30d,
            implied_vol_avg=implied_vol_avg,
            risk_reversal_25d=surface_metrics["risk_reversal_25d"],
            skew_10d=surface_metrics["skew_10d"],
            vol_of_vol=surface_metrics["vol_of_vol"],
            realized_implied_spread=surface_metrics["realized_implied_spread"],
            vol_risk_premium=surface_metrics["vol_risk_premium"],
            vol_regime=vol_regime,
            vol_percentile=vol_percentile,
            optimal_bands=optimal_bands,
            hedge_frequency_modifier=hedge_freq_modifier,
            rationale=rationale
        )
        
        # Update cache
        self.vol_cache[asset] = profile
        self.cache_timestamps[asset] = now
        
        logger.info(f"✅ {asset} volatility profile: {vol_regime} regime ({current_vol:.1%})")
        
        return profile
    
    async def _calculate_realized_volatility(self, asset: str, days: int = 30) -> float:
        """Calculate realized volatility using Bybit historical vol with kline fallback."""
        base_coin = self._normalize_base_coin(asset)
        bybit_vol = await self._get_bybit_historical_volatility(base_coin, days)
        if bybit_vol is not None:
            return bybit_vol
        return await self._calculate_realized_volatility_from_klines(base_coin, days)

    async def _get_bybit_historical_volatility(self, base_coin: str, days: int) -> Optional[float]:
        """Get Bybit historical volatility for a specific period in days."""
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=max(days, 30))
            historical_vol = await self.api.get_historical_vol(
                base_coin=base_coin,
                start_time=start_time,
                end_time=end_time,
                period=days
            )

            if not historical_vol:
                return None

            vol_values = []
            for item in historical_vol:
                if isinstance(item, dict):
                    value = item.get('value')
                    if value:
                        try:
                            vol_values.append(float(value))
                        except (TypeError, ValueError):
                            continue

            if not vol_values:
                return None

            current_vol = vol_values[-1]
            if current_vol > 5.0:
                current_vol = current_vol / 100.0
            return max(0.2, min(current_vol, 5.0))
        except Exception as e:
            # Expected, handled fallback — Bybit option historical-vol is often
            # empty/unavailable per base coin (e.g. ETH returns 0 pts); caller
            # falls back to kline-based realized vol. DEBUG, not per-cycle WARN noise.
            logger.debug(f"Bybit historical volatility unavailable for {base_coin}, using kline fallback: {e}")
            return None

    async def _calculate_realized_volatility_from_klines(self, base_coin: str, days: int = 30) -> float:
        """Calculate realized volatility from klines data."""
        try:
            # Fetch klines for the asset (use USDT pair for linear futures)
            symbol = f"{base_coin}USDT"
            hours_back = days * 24
            klines = await self.api.get_klines(symbol, '1h', hours_back=hours_back)
            
            if not klines or len(klines) < 2:
                logger.warning(f"⚠️ Insufficient klines data for {base_coin}, using fallback")
                return self._get_fallback_volatility(base_coin)
            
            # Calculate log returns
            returns = []
            for i in range(1, len(klines)):
                prev_close = float(klines[i-1].close)
                curr_close = float(klines[i].close)
                if prev_close > 0:
                    log_return = np.log(curr_close / prev_close)
                    returns.append(log_return)
            
            if not returns:
                return self._get_fallback_volatility(base_coin)
            
            # Calculate annualized volatility (hourly data)
            hourly_vol = np.std(returns)
            annualized_vol = hourly_vol * np.sqrt(365 * 24)
            
            # Clamp to reasonable crypto range
            return max(0.2, min(annualized_vol, 5.0))
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculating realized vol for {base_coin}: {e}")
            return self._get_fallback_volatility(base_coin)

    def _normalize_base_coin(self, asset: str) -> str:
        """Normalize asset symbols to base coin (e.g., BTCUSDT -> BTC)."""
        if asset.endswith("USDT"):
            return asset[:-4]
        if "-" in asset:
            return asset.split("-", 1)[0]
        return asset
    
    async def _get_option_prices(self, asset: str):
        """Fetch option prices from the exchange API."""
        try:
            option_prices = await self.api.get_option_prices(asset)
            return option_prices or []
        except Exception as e:
            logger.warning(f"⚠️ Error getting option prices for {asset}: {e}")
            return []

    def _calculate_average_implied_volatility(self, option_prices) -> float:
        """Calculate volume-weighted average implied volatility from options data."""
        if not option_prices:
            return 0.0

        total_volume = 0.0
        weighted_iv = 0.0

        for option in option_prices:
            if option.volume_24h > 0 and option.mark_iv > 0:
                weighted_iv += option.mark_iv * option.volume_24h
                total_volume += option.volume_24h

        if total_volume > 0:
            return weighted_iv / total_volume

        # Fallback: simple average of valid IVs
        valid_ivs = [opt.mark_iv for opt in option_prices if opt.mark_iv > 0]
        return float(np.mean(valid_ivs)) if valid_ivs else 0.0
    
    def _extract_strike_from_symbol(self, symbol: str) -> Optional[float]:
        """Extract strike price from option symbol like 'BTC-30DEC24-70000-C'."""
        try:
            parts = symbol.split('-')
            if len(parts) >= 3:
                strike_str = parts[2]
                return float(strike_str)
        except (ValueError, IndexError):
            pass
        return None

    def _calculate_atm_implied_volatility(self, option_prices, underlying_price: float) -> float:
        """Calculate ATM implied volatility for proper VRP calculation."""
        if not option_prices:
            return 0.0
        
        # Find ATM options (closest to current price)
        atm_options = []
        min_distance = float('inf')
        
        for option in option_prices:
            if option.mark_iv > 0:
                strike = self._extract_strike_from_symbol(option.symbol)
                if strike is not None:
                    distance = abs(strike - underlying_price) / underlying_price
                    if distance < min_distance:
                        min_distance = distance
                    
        # Get all options within 2% of ATM
        atm_threshold = min_distance + 0.02
        for option in option_prices:
            if option.mark_iv > 0:
                strike = self._extract_strike_from_symbol(option.symbol)
                if strike is not None:
                    distance = abs(strike - underlying_price) / underlying_price
                    if distance <= atm_threshold:
                        atm_options.append(option)
        
        if not atm_options:
            return 0.0
        
        # Volume-weighted average of ATM options
        total_volume = sum(opt.volume_24h for opt in atm_options)
        if total_volume > 0:
            weighted_iv = sum(opt.mark_iv * opt.volume_24h for opt in atm_options)
            return weighted_iv / total_volume
        else:
            # Simple average if no volume data
            return float(np.mean([opt.mark_iv for opt in atm_options]))

    def _calculate_vol_surface_metrics(self, option_prices, realized_vol_30d: float, underlying_price: float) -> Dict[str, float]:
        """Calculate surface metrics like RR, skew, vol-of-vol, and VRP."""
        if not option_prices:
            return {
                "risk_reversal_25d": float("nan"),
                "skew_10d": float("nan"),
                "vol_of_vol": float("nan"),
                "realized_implied_spread": float("nan"),
                "vol_risk_premium": float("nan")
            }

        def classify_option(symbol: str) -> Optional[str]:
            if symbol.endswith("-C"):
                return "call"
            if symbol.endswith("-P"):
                return "put"
            return None

        def nearest_iv(target_delta: float, option_type: str) -> Optional[float]:
            candidates = []
            for option in option_prices:
                opt_type = classify_option(option.symbol)
                if opt_type != option_type or option.mark_iv <= 0:
                    continue
                if option.delta is None:
                    continue
                candidates.append((abs(option.delta - target_delta), option.mark_iv))
            if not candidates:
                return None
            return min(candidates, key=lambda x: x[0])[1]

        iv_25_call = nearest_iv(0.25, "call")
        iv_25_put = nearest_iv(-0.25, "put")
        iv_10_call = nearest_iv(0.10, "call")
        iv_10_put = nearest_iv(-0.10, "put")

        risk_reversal_25d = (
            iv_25_call - iv_25_put if iv_25_call is not None and iv_25_put is not None else float("nan")
        )
        skew_10d = (
            iv_10_put - iv_10_call if iv_10_call is not None and iv_10_put is not None else float("nan")
        )

        iv_values = [opt.mark_iv for opt in option_prices if opt.mark_iv > 0]
        vol_of_vol = float(np.std(iv_values)) if len(iv_values) >= 5 else float("nan")

        # Use ATM IV for proper VRP calculation (not volume-weighted average)
        atm_implied_vol = self._calculate_atm_implied_volatility(option_prices, underlying_price)
        
        # VRP calculation: ATM Implied vs Realized (same 30-day horizon)
        realized_implied_spread = atm_implied_vol - realized_vol_30d if realized_vol_30d else float("nan")
        vol_risk_premium = (
            atm_implied_vol / realized_vol_30d - 1
            if realized_vol_30d and realized_vol_30d > 0 and atm_implied_vol > 0
            else float("nan")
        )

        return {
            "risk_reversal_25d": risk_reversal_25d,
            "skew_10d": skew_10d,
            "vol_of_vol": vol_of_vol,
            "realized_implied_spread": realized_implied_spread,
            "vol_risk_premium": vol_risk_premium
        }
    
    async def _calculate_vol_percentile(self, asset: str, current_vol: float) -> float:
        """Calculate where current volatility sits vs historical distribution."""
        try:
            # Fetch longer historical data
            symbol = f"{asset}USDT"
            hours_back = self.config.percentile_window_days * 24
            klines = await self.api.get_klines(symbol, "1h", hours_back=hours_back)
            
            if not klines or len(klines) < 100:
                return 50.0  # Default percentile
            
            # Calculate rolling 7-day volatilities
            window_size = 24 * 7  # 7 days in hours
            historical_vols = []
            
            for i in range(window_size, len(klines)):
                window_klines = klines[i-window_size:i]
                returns = []
                
                for j in range(1, len(window_klines)):
                    prev_close = float(window_klines[j-1].close)
                    curr_close = float(window_klines[j].close)
                    if prev_close > 0:
                        returns.append(np.log(curr_close / prev_close))
                
                if returns:
                    vol = np.std(returns) * np.sqrt(365 * 24)
                    historical_vols.append(vol)
            
            if not historical_vols:
                return 50.0
            
            # Calculate percentile
            percentile = (np.searchsorted(np.sort(historical_vols), current_vol) / len(historical_vols)) * 100
            return max(0, min(100, percentile))
            
        except Exception as e:
            logger.warning(f"⚠️ Error calculating vol percentile for {asset}: {e}")
            return 50.0
    
    def _classify_vol_regime(self, volatility: float) -> str:
        """Classify volatility into regime categories."""
        if volatility < self.config.low_vol_threshold:
            return "LOW"
        elif volatility < self.config.medium_vol_threshold:
            return "MEDIUM"
        elif volatility < self.config.high_vol_threshold:
            return "HIGH"
        else:
            return "EXTREME"
    
    def _generate_asset_bands(self, asset: str, volatility: float, regime: str, percentile: float) -> List[float]:
        """Generate optimal delta bands based on asset characteristics."""
        
        # Base bands for different volatility regimes
        base_bands = {
            "LOW": [0.10, 0.20, 0.35, 0.50, 0.70],           # Tighter bands for low vol
            "MEDIUM": [0.15, 0.30, 0.50, 0.75, 1.00],        # Standard crypto bands
            "HIGH": [0.25, 0.50, 0.80, 1.20, 1.60],          # Wider bands for high vol
            "EXTREME": [0.40, 0.80, 1.20, 1.80, 2.50]        # Very wide bands for extreme vol
        }
        
        bands = base_bands[regime].copy()
        
        # Asset-specific adjustments
        if asset == "BTC":
            # BTC is typically less volatile than alts
            bands = [b * 0.9 for b in bands]
        elif asset == "ETH":
            # ETH baseline
            pass
        elif asset == "SOL":
            # SOL is typically more volatile  
            bands = [b * 1.2 for b in bands]
        else:
            # Other alts - assume higher volatility
            bands = [b * 1.3 for b in bands]
        
        # Percentile adjustments
        if percentile > 80:  # Current vol is in top 20%
            bands = [b * 1.2 for b in bands]  # Wider bands
        elif percentile < 20:  # Current vol is in bottom 20%
            bands = [b * 0.8 for b in bands]  # Tighter bands
        
        # Round to reasonable precision
        bands = [round(b, 2) for b in bands]
        
        return sorted(bands)
    
    def _calculate_hedge_frequency_modifier(self, volatility: float, regime: str) -> float:
        """Calculate hedge frequency modifier based on volatility."""
        
        # Base modifiers by regime
        base_modifiers = {
            "LOW": 0.7,      # Hedge less frequently in low vol
            "MEDIUM": 1.0,   # Standard frequency
            "HIGH": 1.3,     # Hedge more frequently in high vol
            "EXTREME": 1.6   # Much higher frequency in extreme vol
        }
        
        modifier = base_modifiers[regime]
        
        # Fine-tune based on actual volatility
        if volatility > 2.0:  # Above 200%
            modifier *= 1.2
        elif volatility < 0.3:  # Below 30%
            modifier *= 0.8
        
        return modifier
    
    def _generate_volatility_rationale(self, asset: str, current_vol: float, regime: str, 
                                     percentile: float, vol_7d: float, vol_30d: float) -> str:
        """Generate human-readable rationale for volatility analysis."""
        
        rationale_parts = []
        
        # Current regime
        rationale_parts.append(f"{asset} in {regime} volatility regime ({current_vol:.1%} annualized)")
        
        # Historical context
        if percentile > 80:
            rationale_parts.append(f"Current vol in top 20% historically (percentile: {percentile:.0f})")
        elif percentile < 20:
            rationale_parts.append(f"Current vol in bottom 20% historically (percentile: {percentile:.0f})")
        else:
            rationale_parts.append(f"Vol near historical median (percentile: {percentile:.0f})")
        
        # Recent trend
        if vol_7d > vol_30d * 1.2:
            rationale_parts.append("Recent vol spike detected - wider bands recommended")
        elif vol_7d < vol_30d * 0.8:
            rationale_parts.append("Vol cooling down - can use tighter bands")
        
        # Asset-specific note
        asset_characteristics = {
            "BTC": "BTC typically less volatile than alts",
            "ETH": "ETH moderate volatility profile", 
            "SOL": "SOL higher volatility than major pairs"
        }
        
        if asset in asset_characteristics:
            rationale_parts.append(asset_characteristics[asset])
        
        return ". ".join(rationale_parts)
    
    def _get_fallback_volatility(self, asset: str) -> float:
        """Fallback volatility estimates when data is unavailable."""
        fallbacks = {
            "BTC": 0.6,   # 60% annual
            "ETH": 0.8,   # 80% annual
            "SOL": 1.2,   # 120% annual
        }
        return fallbacks.get(asset, 1.0)  # Default 100% for unknown assets
    
    def get_cached_profiles(self) -> Dict[str, VolatilityProfile]:
        """Get all cached volatility profiles."""
        return self.vol_cache.copy()
    
    def format_profile_summary(self, profile: VolatilityProfile) -> str:
        """Format volatility profile for display."""
        # Validate VRP calculation for display
        vrp_status = ""
        if np.isnan(profile.vol_risk_premium):
            vrp_status = " (data unavailable - check ATM IV and RV)"
        elif abs(profile.vol_risk_premium) > 2.0:  # VRP > 200% is suspicious
            vrp_status = " (warning: extreme VRP - validate data)"
        
        return (
            f"📊 {profile.asset} Volatility Profile:\\n"
            f"  Regime: {profile.vol_regime}\\n"
            f"  7d Realized: {profile.realized_vol_7d:.1%}\\n"
            f"  30d Realized: {profile.realized_vol_30d:.1%}\\n"
            f"  Implied (avg): {profile.implied_vol_avg:.1%}\\n"
            f"  25d RR: {profile.risk_reversal_25d:.2%}{'(invalid)' if np.isnan(profile.risk_reversal_25d) else ''}\\n"
            f"  10d Skew: {profile.skew_10d:.2%}{'(invalid)' if np.isnan(profile.skew_10d) else ''}\\n"
            f"  Vol-of-Vol: {profile.vol_of_vol:.2%}{'(invalid)' if np.isnan(profile.vol_of_vol) else ''}\\n"
            f"  IV-RV Spread: {profile.realized_implied_spread:.2%}{'(invalid)' if np.isnan(profile.realized_implied_spread) else ''}\\n"
            f"  Vol Risk Premium: {profile.vol_risk_premium:.2%}{vrp_status}\\n"
            f"  Historical %ile: {profile.vol_percentile:.0f}\\n"
            f"  Optimal Bands: {profile.optimal_bands}\\n"
            f"  Rationale: {profile.rationale}"
        )
