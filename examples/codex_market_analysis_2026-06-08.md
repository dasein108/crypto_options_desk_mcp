# Crypto Options Market Analysis Update

Generated: 2026-06-08 01:15 UTC / 09:15 Asia/Makassar

Source: trading_mcp live derivatives and options analysis.

Reference snapshot: `codex_market_analysis_2026-06-07.md`

Note: This is not financial advice. These are risk-defined trade ideas based on current derivatives structure.

## Current Position State

No open options positions were reported by trading_mcp.

## What Changed

BTC moved from about 62.2k to 63.0k, pressing into the prior 63,000 resistance area. GEX support moved lower from 61,500 to 61,000, the flip level moved up from 62,189 to 62,317, and the 70% breakout probability remains. However, OI and liquidity weakened further: BTC OI percentile dropped from prior 31.9/8.6 readings to about 1.9. BTC is closer to resistance, but less well-supported by market participation.

ETH moved from about 1,635 to 1,681. This remains the cleanest bullish continuation setup. OI rose from 893k to 908k, remains at the 100th percentile, and liquidity improved from 94 to 96. Funding is still negative but less extreme, moving from about -9.7% annualized to -6.7%. ETH is now approaching the key 1,725 resistance and confirmation level from the June 7 snapshot.

SOL moved from about 65.2 to 65.9. Sentiment strengthened materially: score moved from 21 to 36, confidence from 0.69 to 0.81, and long-short positioning is now very crowded. However, OI fell from 8.53M to 8.25M, and liquidity score dropped from 56 to 44. SOL is more bullish-looking, but also more fragile and crowded.

## Updated Trade View

The prior ETH 1650 straddle is still valid, but it is no longer the top-ranked tool output. Spot has moved above the strike, so it is less centered. Cost is almost unchanged: 197.64 yesterday versus 198.63 now. Breakevens moved slightly to 1451.37 / 1848.63. ETH remains the core trade.

For a fresh ETH entry, consider one of two approaches:

- Keep the `ETH-26JUN26-1650-C` + `ETH-26JUN26-1650-P` straddle for liquidity and continuity.
- Shift closer/up to the `ETH-26JUN26-1750-C` + `ETH-26JUN26-1750-P` straddle for a cleaner upside-biased volatility trade. Current cost is 201.49, with breakevens at 1548.51 / 1951.49.

BTC `56000/69000` strangle improved slightly on cost: 1521.11 yesterday to 1400.20 now, with breakevens at 54599.80 / 70400.20. It remains a good defined-risk breakout structure, but size should not increase because BTC participation is deteriorating.

SOL `56/84` strangle is basically unchanged in price: 1.48 yesterday versus 1.49 now. However, liquidity score dropped from 90 to 60 in the options analysis, while spot market liquidity also weakened. Reduce SOL allocation or skip unless comfortable with execution slippage.

## Recommended Positions

| Priority | Trade | Expiry | Est. Cost | Breakevens | View |
|---|---:|---:|---:|---:|---|
| 1 | Long `ETH-26JUN26-1650-C` + long `ETH-26JUN26-1650-P` | Jun 26 | `198.63` | `1451.37 / 1848.63` | Core ETH volatility continuation trade |
| 1A | Alternative: long `ETH-26JUN26-1750-C` + long `ETH-26JUN26-1750-P` | Jun 26 | `201.49` | `1548.51 / 1951.49` | Cleaner upside-biased ETH volatility entry |
| 2 | Long `BTC-26JUN26-56000-P` + long `BTC-26JUN26-69000-C` | Jun 26 | `1400.20` | `54599.80 / 70400.20` | BTC breakout hedge, but weaker participation argues for smaller size |
| 3 | Long `SOL-26JUN26-56-P` + long `SOL-26JUN26-84-C` | Jun 26 | `1.49` | `54.51 / 85.49` | Small convex SOL trade only; liquidity worsened |

## Updated Allocation

- 65% of options risk budget: ETH volatility, using either the Jun 26 1650 straddle or Jun 26 1750 straddle.
- 25%: BTC Jun 26 56k/69k long strangle.
- 10% or less: SOL Jun 26 56/84 long strangle.

## Main Takeaway

ETH got stronger and remains the highest-quality setup. BTC is closer to breakout but weaker under the surface because participation and liquidity deteriorated. SOL became more crowded with worse liquidity, so it should be sized smaller than before or skipped.

## Risk Controls

- Treat the full premium as max loss.
- Exit long straddles or strangles if premium decays 35-45% without spot expansion.
- Take partial profits at 80-120% premium gain.
- For ETH, bullish confirmation improves above 1,725; failure below 1,600 weakens the setup materially.
- For BTC, watch the 61,000-63,000 GEX zone. A clean hold above 63,000 improves breakout odds, but weak OI makes false breaks more likely.
- For SOL, avoid chasing if spreads widen; liquidity and crowding are the main risks.
