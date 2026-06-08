# Crypto Options Market Update — Delta Analysis

**Date:** 08 Jun 2026, ~01:15 UTC
**Compares against:** 07 Jun 2026, 14:34 UTC snapshot (~11h elapsed)
**Author view:** Hedge fund manager
**Source:** quant_analyst_tools (Bybit live data)

---

## What Changed

| Metric | Then (14:34) | Now (01:15) | Δ |
|---|---|---|---|
| BTC spot | $62,629 | $63,337 | +1.1% |
| ETH spot | $1,630 | $1,690 | +3.7% |
| BTC RSI (4h) | 44.6 | 50.9 | bouncing |
| ETH RSI (4h) | 38.4 | 51.8 | bouncing hard |
| BTC stoch K | 76.7 | 81.6 | extended |
| ETH stoch K | 51.4 | 85.8 | extended |
| BTC ATM IV | 66.7% | 66.5% | flat |
| ETH ATM IV | 87.0% | **93.6%** | +6.6 pts |
| BTC IV−RV (30d) | +23.1 | +21.7 | slightly richer RV |
| ETH IV−RV (30d) | +26.5 | **+31.5** | richer premium |
| BTC net GEX | -$224.7M | -$136.9M | less short gamma |
| ETH net GEX | -$95.2M | -$63.2M | less short gamma |
| BTC funding | -0.019 (neg) | +0.008 (flipped +) | longs paying now |
| BTC OI | 57,160 | 53,571 (-7.3%) | positions closing out |

---

## Read

A **low-conviction relief bounce**, mostly led by ETH. Both assets put in the same shape: oversold RSIs lifted to ~51, MACD histograms turned up, and both now flag a "STRONG_UPTREND" signal on the 4h. ETH did the heavy lifting (+3.7%, +6% on the 5-day) and is now poking the top of its Bollinger band (bb_position 73.6) with stochastics at 86 — extended short-term.

But the trend backbone is unchanged and still bearish: both sit below SMA50 (BTC -4.6%, ETH -6.5%), and the 20/50 cross is still -7% to -10%. This is a bounce inside a downtrend, not a reversal. ADX easing from 68 to ~59 says the prior down-impulse is losing steam, not that bulls have taken over.

Two structural shifts matter more than the price tick:

1. **Short gamma is decaying** — BTC net GEX nearly halved (-224 → -137M), ETH similar. Dealers are less short, so the move-amplification risk that made naked selling dangerous is *lower* now than this afternoon. Spot still sits right on both flip levels (BTC 63.3k vs 62.3k flip; ETH 1690 vs 1681), so it's still a pin, just a less explosive one.

2. **ETH vol got richer, not cheaper, into the rally** — ATM IV +6.6 pts and the 30d term premium widened to +31.5. IV rising on an up-move is unusual and means the ETH premium-selling edge actually *improved*. BTC funding flipped positive (longs now paying), and OI dropped 7% — capitulation/deleveraging, consistent with a short-covering bounce rather than fresh conviction longs.

The trap is still there: covered-call signal is still a hard no-go, short-window RV still ~78%, term structure still backwardated (-22.8%, even steeper). Near-term realized is hot despite the calm-looking 30d window.

---

## Implication for the Recommendations

Nothing breaks; the **ETH put-credit-spread thesis (#1) is stronger now** — higher IV, wider premium, less short gamma, and price has lifted off the 1500–1600 shelf giving more cushion below the short strike. Could sell the ETH put spread slightly higher (e.g. 1550/1450) and still sit under support.

The caution is the extended stochastics — if legging in, the bounce being this stretched means a better ETH IV entry may come on a pullback rather than chasing here. BTC is more of a coin-flip at the flip level; the conservative 58k/55k put spread still holds but with thinner edge than ETH.
