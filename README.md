# trading-mcp

A **Model Context Protocol** server that exposes a quant crypto-options desk's read-side analytics as
typed, audited, **dry-run-by-default** tools an LLM agent can call — one surface over options flow,
gamma exposure, technicals, portfolio greeks, and scenario analysis.

> Extracted from a private multi-strategy trading desk. This is the **analytics surface** — it contains
> no strategy signals, thresholds, or alpha. The server is a *thin facade*; all math lives in the
> bundled libraries (`options_lib`, `indicators_lib`, `portfolio_lib`, `bybit_api`), the same code the
> (private) strategy bots import directly. One implementation, surfaced two ways.

## Why MCP

An LLM agent reasoning about a book needs GEX walls, vanna flow, skew, vol surface, indicators, and
portfolio greeks — but you don't want it reaching into internals or calling exchange APIs ad hoc. MCP
gives it **one typed tool surface** with a uniform `{success, data, timestamp}` envelope, read-only by
default, and key-gated for anything that could touch a live book.

## The 22 tools

| Group | Tools | What the agent gets |
|---|---|---|
| Options flow | 5 | GEX walls & flip level, vanna, delta-imbalance flow, skew, vol surface |
| Technical | 1 | EMA stack, RSI, MACD, ATR, Bollinger, ADX, Hurst, Z-score |
| Market data | 2 | klines, options chain |
| Sentiment & positioning | 3 | funding, OI, sentiment |
| Portfolio | 2 | aggregate greeks, scenario analysis |
| User positions | 2 | live book *(API-key gated)* |
| Vol selling | 2 | IV/RV spread, covered-call signal |
| Strategy | 4 | straddle / strangle / spread / portfolio strategy analysis |
| Meta | 1 | server info |

## Run

```bash
pip install -e .
cp .env.example .env          # optional — only user-position tools need keys
trading-mcp                   # starts the MCP server (stdio)
```

Point any MCP client (Claude Desktop, etc.) at the `trading-mcp` command. Read tools work with **no
credentials**; only the two user-position tools require a Bybit API key.

## Safety model

- **Uniform envelope** — every tool returns `{success, data, timestamp}`; failures are structured, never free text.
- **Read-first** — the analytics surface has no side effects.
- **Key-gated** — live-book tools require an API key the read tools don't, so an unconfigured agent physically cannot move money.

## Test

```bash
pip install -e ".[dev]" && pytest
```

## Architecture

```
mcp_trading/         thin MCP facade (server.py = 22 @mcp.tool wrappers) + orchestrator
  ├─ options_lib/    GEX · vanna · skew · flow · vol surface · strategy classification · pricing
  ├─ indicators_lib/ technicals + sentiment
  ├─ portfolio_lib/  portfolio engine + greeks + scenario analysis
  └─ bybit_api/      exchange client (klines, chain, funding, OI, positions)
```

## License

MIT.
