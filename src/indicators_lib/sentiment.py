"""
Market Sentiment Analysis Module

Analyzes market sentiment using long-short ratio, open interest, and funding data.
Provides compact, percentile-based metrics optimized for LLM consumption.
"""

from typing import List, Dict, Any, Optional
import numpy as np
from datetime import datetime, timezone
from scipy import stats

# API client is duck-typed (passed at construction)
import logging

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Analyze market sentiment using long-short ratio, OI, and funding data."""
    
    def __init__(self, api=None):
        """Initialize sentiment analyzer
        
        Args:
            api: Bybit API adapter instance
        """
        if api is None:
            raise ValueError("SentimentAnalyzer requires an API client")
        self.api = api

    def calculate_percentiles(self, current_value: float, historical_data: List[float]) -> Dict[str, float]:
        """Calculate percentile rankings for current value"""
        if not historical_data or len(historical_data) < 2:
            return {
                "percentile_24h": 50.0,
                "percentile_7d": 50.0, 
                "percentile_30d": 50.0
            }
        
        # Calculate percentiles for different time windows
        data_24h = historical_data[-144:] if len(historical_data) >= 144 else historical_data  # Last 24h (10min intervals)
        data_7d = historical_data[-1008:] if len(historical_data) >= 1008 else historical_data  # Last 7d
        data_30d = historical_data  # All available data (up to 30d)
        
        return {
            "percentile_24h": stats.percentileofscore(data_24h, current_value),
            "percentile_7d": stats.percentileofscore(data_7d, current_value),
            "percentile_30d": stats.percentileofscore(data_30d, current_value)
        }

    def calculate_extremity_score(self, percentiles: Dict[str, float]) -> int:
        """Calculate how extreme current conditions are (0-100)"""
        # Use 30-day percentile as primary reference
        p30 = percentiles.get("percentile_30d", 50.0)
        
        # Distance from center (50th percentile)
        distance_from_center = abs(p30 - 50.0)
        
        # Convert to 0-100 scale (50 = maximum extremity)
        extremity_score = min(int(distance_from_center * 2), 100)
        
        return extremity_score

    def classify_extremity(self, score: int) -> str:
        """Classify extremity level"""
        if score >= 80:
            return "extreme"
        elif score >= 60:
            return "high" 
        elif score >= 40:
            return "moderate"
        else:
            return "normal"

    def classify_sentiment(self, long_ratio: float) -> str:
        """Classify market sentiment based on long-short ratio"""
        if long_ratio > 0.65:
            return "extremely_bullish"
        elif long_ratio > 0.55:
            return "bullish"
        elif long_ratio > 0.45:
            return "neutral" 
        elif long_ratio > 0.35:
            return "bearish"
        else:
            return "extremely_bearish"

    def calculate_trend_direction(self, values: List[float], window: int = 5) -> str:
        """Calculate trend direction from recent values"""
        if len(values) < window:
            return "stable"
            
        recent_values = values[-window:]
        if len(recent_values) < 2:
            return "stable"
            
        # Simple linear regression to determine trend
        x = np.arange(len(recent_values))
        slope, _, _, _, _ = stats.linregress(x, recent_values)
        
        if slope > 0.001:
            return "increasing"
        elif slope < -0.001:
            return "decreasing"
        else:
            return "stable"

    def analyze_long_short_sentiment(self, ls_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze long-short ratio for sentiment signals"""
        if not ls_data:
            return {
                "current_ls_ratio": 1.0,
                "ls_percentile_24h": 50.0,
                "ls_percentile_7d": 50.0,
                "ls_percentile_30d": 50.0,
                "positioning_extremity": 0,
                "trend_direction": "stable",
                "sentiment_category": "neutral"
            }

        # Get current and historical values
        current_data = ls_data[-1]
        current_ratio = current_data.get('long_ratio', 0.5)
        
        # Extract historical long ratios
        historical_ratios = [item.get('long_ratio', 0.5) for item in ls_data]
        
        # Calculate percentiles
        percentiles = self.calculate_percentiles(current_ratio, historical_ratios)
        
        # Calculate extremity and trend
        extremity = self.calculate_extremity_score(percentiles)
        trend = self.calculate_trend_direction(historical_ratios)
        sentiment = self.classify_sentiment(current_ratio)
        
        return {
            "current_ls_ratio": round(current_ratio, 3),
            "ls_percentile_24h": round(percentiles["percentile_24h"], 1),
            "ls_percentile_7d": round(percentiles["percentile_7d"], 1),
            "ls_percentile_30d": round(percentiles["percentile_30d"], 1),
            "positioning_extremity": extremity,
            "trend_direction": trend,
            "sentiment_category": sentiment
        }

    def analyze_open_interest_trends(self, oi_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze open interest trends and divergences"""
        if not oi_data:
            return {
                "current_oi": 0.0,
                "oi_change_24h_pct": 0.0,
                "oi_percentile_7d": 50.0,
                "oi_percentile_30d": 50.0,
                "liquidity_score": 50,
                "oi_momentum": "stable",
                "market_engagement": "medium"
            }

        # Get current and historical values
        current_data = oi_data[-1]
        current_oi = current_data.get('open_interest', 0.0)
        
        # Calculate 24h change
        if len(oi_data) >= 144:  # 24h of 10min data
            oi_24h_ago = oi_data[-144].get('open_interest', current_oi)
            oi_change_24h_pct = ((current_oi - oi_24h_ago) / oi_24h_ago * 100) if oi_24h_ago > 0 else 0.0
        else:
            oi_change_24h_pct = 0.0
        
        # Extract historical OI values
        historical_oi = [item.get('open_interest', 0.0) for item in oi_data]
        
        # Calculate percentiles
        percentiles = self.calculate_percentiles(current_oi, historical_oi)
        
        # Calculate trend and momentum
        trend = self.calculate_trend_direction(historical_oi)
        
        # Liquidity score based on OI percentile and stability
        oi_std = np.std(historical_oi[-144:]) if len(historical_oi) >= 144 else 0
        oi_cv = oi_std / current_oi if current_oi > 0 else 1
        stability_score = max(0, 100 - int(oi_cv * 1000))
        liquidity_score = int((percentiles["percentile_30d"] + stability_score) / 2)
        
        # Market engagement classification
        if percentiles["percentile_30d"] > 75:
            engagement = "high"
        elif percentiles["percentile_30d"] > 40:
            engagement = "medium"
        else:
            engagement = "low"
        
        return {
            "current_oi": current_oi,
            "oi_change_24h_pct": round(oi_change_24h_pct, 1),
            "oi_percentile_7d": round(percentiles["percentile_7d"], 1),
            "oi_percentile_30d": round(percentiles["percentile_30d"], 1),
            "liquidity_score": min(100, max(0, liquidity_score)),
            "oi_momentum": trend,
            "market_engagement": engagement
        }

    def analyze_funding_rates(self, funding_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze funding rate patterns and extremes"""
        if not funding_data:
            return {
                "current_rate": 0.0,
                "funding_percentile_24h": 50.0,
                "funding_percentile_7d": 50.0,
                "funding_percentile_30d": 50.0,
                "funding_extremity": 0,
                "annualized_cost": 0.0,
                "stress_indicator": False,
                "carry_opportunity": "neutral"
            }

        # Get current and historical values
        current_data = funding_data[-1]
        current_rate = current_data.get('funding_rate', 0.0)
        
        # Extract historical funding rates
        historical_rates = [item.get('funding_rate', 0.0) for item in funding_data]
        
        # Calculate percentiles
        percentiles = self.calculate_percentiles(current_rate, historical_rates)
        
        # Calculate extremity
        extremity = self.calculate_extremity_score(percentiles)
        
        # Annualized cost (3 times per day)
        annualized_cost = current_rate * 365 * 3 * 100  # Convert to percentage
        
        # Stress indicator (extreme funding rates)
        stress_indicator = abs(current_rate) > 0.0075  # 0.75% (8h)
        
        # Carry opportunity classification
        if current_rate > 0.005:  # > 0.5%
            carry_opportunity = "bearish"  # High cost to be long, opportunity to short
        elif current_rate < -0.005:  # < -0.5%
            carry_opportunity = "bullish"  # Paid to be long
        else:
            carry_opportunity = "neutral"
        
        return {
            "current_rate": round(current_rate, 6),  # Preserve 6 decimal places for small rates
            "funding_percentile_24h": round(percentiles.get("percentile_24h", 50.0), 1),
            "funding_percentile_7d": round(percentiles.get("percentile_7d", 50.0), 1),
            "funding_percentile_30d": round(percentiles.get("percentile_30d", 50.0), 1),
            "funding_extremity": extremity,
            "annualized_cost": round(annualized_cost, 3),  # Increased precision for annualized cost
            "stress_indicator": stress_indicator,
            "carry_opportunity": carry_opportunity
        }

    def combined_sentiment_score(self, ls_data: List[Dict[str, Any]], oi_data: List[Dict[str, Any]], 
                                 funding_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate combined sentiment score"""
        
        # Analyze each component
        ls_analysis = self.analyze_long_short_sentiment(ls_data)
        oi_analysis = self.analyze_open_interest_trends(oi_data)
        funding_analysis = self.analyze_funding_rates(funding_data)
        
        # Calculate weighted sentiment score (-100 to +100)
        ls_component = (ls_analysis["current_ls_ratio"] - 0.5) * 200 * 0.4  # 40% weight
        
        # OI component based on momentum
        if oi_analysis["oi_momentum"] == "increasing":
            oi_component = 20 * 0.3  # Positive for increasing OI
        elif oi_analysis["oi_momentum"] == "decreasing":
            oi_component = -20 * 0.3  # Negative for decreasing OI
        else:
            oi_component = 0
        
        # Funding component (inverted - high funding is bearish)
        funding_component = np.tanh(-funding_analysis["current_rate"] / 0.001) * 100 * 0.3  # 30% weight
        
        total_score = ls_component + oi_component + funding_component
        sentiment_score = int(np.clip(total_score, -100, 100))
        
        # Classification
        if sentiment_score > 50:
            classification = "strongly_bullish"
        elif sentiment_score > 20:
            classification = "bullish"
        elif sentiment_score > -20:
            classification = "neutral"
        elif sentiment_score > -50:
            classification = "bearish"
        else:
            classification = "strongly_bearish"
        
        # Confidence based on extremity scores
        avg_extremity = (
            ls_analysis["positioning_extremity"] + 
            funding_analysis["funding_extremity"]
        ) / 2
        confidence = min(0.95, max(0.3, avg_extremity / 100))
        
        # Key insights
        insights = []
        if ls_analysis["positioning_extremity"] > 70:
            direction = "bullish" if ls_analysis["current_ls_ratio"] > 0.5 else "bearish"
            insights.append(f"Extreme {direction} positioning detected")
        
        if funding_analysis["stress_indicator"]:
            insights.append("Funding stress indicator active")
            
        if oi_analysis["market_engagement"] == "high" and oi_analysis["oi_momentum"] == "increasing":
            insights.append("Strong market participation supports trend")
        elif oi_analysis["market_engagement"] == "low":
            insights.append("Low market engagement, reduced liquidity")
            
        if not insights:
            insights.append(f"{classification.replace('_', ' ').title()} sentiment with normal conditions")
        
        return {
            "sentiment_score": sentiment_score,
            "sentiment_classification": classification,
            "confidence_level": round(confidence, 2),
            "positioning": ls_analysis,
            "open_interest": oi_analysis,
            "funding": funding_analysis,
            "key_insights": insights
        }

    async def get_market_sentiment_analysis(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """Get comprehensive market sentiment analysis"""
        try:
            # Fetch all sentiment data in parallel
            import asyncio
            
            tasks = [
                self.api.get_long_short_ratio_data(symbol=symbol, hours_back=24),
                self.api.get_open_interest_data(symbol=symbol, hours_back=24),
                self.api.get_funding_rate_history(symbol=symbol, hours_back=168)  # 7 days
            ]
            
            ls_data, oi_data, funding_data = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle exceptions
            if isinstance(ls_data, Exception):
                logger.error(f"Error fetching long-short data: {ls_data}")
                ls_data = []
            if isinstance(oi_data, Exception):
                logger.error(f"Error fetching OI data: {oi_data}")
                oi_data = []
            if isinstance(funding_data, Exception):
                logger.error(f"Error fetching funding data: {funding_data}")
                funding_data = []
            
            # Generate analysis
            analysis = self.combined_sentiment_score(ls_data, oi_data, funding_data)
            
            return {
                "success": True,
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "analysis_period": "24h",
                **analysis
            }
            
        except Exception as e:
            logger.error(f"Error in sentiment analysis for {symbol}: {e}")
            return {
                "success": False,
                "symbol": symbol,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }

    async def get_open_interest_analysis(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """Get open interest analysis with trend detection"""
        try:
            oi_data = await self.api.get_open_interest_data(symbol=symbol, hours_back=24)
            analysis = self.analyze_open_interest_trends(oi_data)
            
            # Market health interpretation
            if analysis["liquidity_score"] > 75:
                market_health = "healthy_growth"
                liquidity_condition = "abundant"
            elif analysis["liquidity_score"] > 50:
                market_health = "stable"
                liquidity_condition = "adequate"
            else:
                market_health = "declining"
                liquidity_condition = "limited"
            
            # Trading implications
            trading_implications = []
            if analysis["oi_momentum"] == "increasing" and analysis["market_engagement"] == "high":
                trading_implications.append("Strong market participation supports trend continuation")
                trading_implications.append("Good liquidity conditions for large position management")
            elif analysis["oi_momentum"] == "decreasing":
                trading_implications.append("Declining participation may signal trend weakness")
            else:
                trading_implications.append("Stable market conditions")
            
            return {
                "success": True,
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "current_metrics": {
                    "open_interest": analysis["current_oi"],
                    "daily_change_pct": analysis["oi_change_24h_pct"]
                },
                "statistical_analysis": {
                    "oi_percentile_7d": analysis["oi_percentile_7d"],
                    "oi_percentile_30d": analysis["oi_percentile_30d"],
                    "volatility_level": "medium"  # Could be calculated from OI volatility
                },
                "trend_analysis": {
                    "direction": analysis["oi_momentum"],
                    "sustainability": "moderate" if analysis["liquidity_score"] > 60 else "weak"
                },
                "liquidity_metrics": {
                    "liquidity_score": analysis["liquidity_score"],
                    "market_depth": "good" if analysis["liquidity_score"] > 70 else "fair",
                    "participation": analysis["market_engagement"]
                },
                "interpretation": {
                    "market_health": market_health,
                    "liquidity_condition": liquidity_condition,
                    "participation_trend": analysis["oi_momentum"]
                },
                "trading_implications": trading_implications
            }
            
        except Exception as e:
            logger.error(f"Error in OI analysis for {symbol}: {e}")
            return {
                "success": False,
                "symbol": symbol,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }

    async def get_funding_rate_analysis(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """Get funding rate analysis with extremes and carry opportunities"""
        try:
            funding_data = await self.api.get_funding_rate_history(symbol=symbol, hours_back=168)
            analysis = self.analyze_funding_rates(funding_data)
            
            # Market regime classification
            if analysis["funding_extremity"] > 80:
                funding_regime = "extreme_positive" if analysis["current_rate"] > 0 else "extreme_negative"
            elif analysis["funding_extremity"] > 60:
                funding_regime = "positive" if analysis["current_rate"] > 0 else "negative"
            else:
                funding_regime = "normal"
            
            # Trading signals
            trading_signals = []
            if analysis["stress_indicator"]:
                if analysis["current_rate"] > 0:
                    trading_signals.append("Extreme positive funding suggests overheating")
                    trading_signals.append("Consider short positions or mean reversion")
                else:
                    trading_signals.append("Extreme negative funding suggests oversold conditions")
                    trading_signals.append("Consider long positions")
            else:
                trading_signals.append("Normal funding conditions, no stress indicators")
            
            if abs(analysis["current_rate"]) < 0.0001:  # Very low funding
                trading_signals.append("Minimal funding costs for position holding")
            
            return {
                "success": True,
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "current_funding": {
                    "rate": analysis["current_rate"],  # Already rounded to 6 decimal places
                    "annualized_pct": analysis["annualized_cost"]  # Already rounded to 3 decimal places
                },
                "historical_context": {
                    "percentile_24h": analysis["funding_percentile_24h"],
                    "percentile_7d": analysis["funding_percentile_7d"],
                    "percentile_30d": analysis["funding_percentile_30d"],
                    "extremity_score": analysis["funding_extremity"]
                },
                "stress_indicators": {
                    "stress_level": "high" if analysis["stress_indicator"] else "low",
                    "panic_funding": analysis["stress_indicator"]
                },
                "carry_analysis": {
                    "opportunity_score": 100 - analysis["funding_extremity"],  # Lower extremity = better opportunity
                    "direction": analysis["carry_opportunity"],
                    "annual_cost_long": analysis["annualized_cost"],
                    "annual_yield_short": -analysis["annualized_cost"]
                },
                "market_insights": {
                    "funding_regime": funding_regime,
                    "speculation_level": "high" if analysis["funding_extremity"] > 60 else "moderate"
                },
                "trading_signals": trading_signals
            }
            
        except Exception as e:
            logger.error(f"Error in funding analysis for {symbol}: {e}")
            return {
                "success": False,
                "symbol": symbol,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }