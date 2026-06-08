# Crypto Options Desk MCP

A **Model Context Protocol (MCP)** server that gives an LLM agent one typed, audited, read-only-by-default
tool surface over a quant crypto-options desk's analytics: gamma exposure, vanna, skew, vol surface,
options flow, technicals, portfolio greeks, scenario analysis, vol-selling signals, and live positions.

Point Claude (Desktop or Code) at it and ask *"give me a BTC options market memo"* — the agent calls the
tools itself and reasons over real Bybit data.

**What it actually does, end to end:** the LLM drives the whole desk. It calls the flow tools (GEX, vanna,
skew, vol surface) to read dealer positioning, the sentiment/funding/OI tools to read the crowd, the
technicals for trend, and the IV-RV / vol-selling / strategy tools to find an edge — then it cross-checks
those numbers against each other and writes a trader-grade memo: regime call, the structural shifts that
matter, defined-risk trade ideas with strikes/breakevens, an allocation, and a risk checklist. With a
read-only API key it also pulls your live book and folds current positions into the same analysis. The
math is identical to what the (private) strategy bots run — the agent just narrates and reasons over it.

See the [`examples/`](examples/) folder for real outputs: full market memos from both Claude and Codex
(`*_market_analysis_2026-06-07.md`) and the **delta updates** they produced ~11h later
(`*_market_analysis_2026-06-08.md`) — each diffs the new snapshot against the prior one (spot, IV, GEX,
funding, OI) and tells you what *changed* and why it matters, not just where the market is.

> Extracted from a private multi-strategy trading desk. This is the **analytics surface** only — no
> strategy signals, thresholds, or alpha. The server is a *thin facade*; all math lives in the bundled
> libraries (`options_lib`, `indicators_lib`, `portfolio_lib`, `bybit_api`) — the same code the (private)
> strategy bots import directly. One implementation, surfaced two ways.

---

## Contents
- [Install](#install)
- [Use with Claude](#use-with-claude) (Desktop & Code)
- [Keep the session rolling](#keep-the-session-rolling) ⭐
- [Example outputs](#example-outputs)
- [API key setup](#api-key-setup-optional) (optional)
- [The 22 tools](#the-22-tools)
- [Bonus: the research prompt](#bonus-the-research-prompt)
- [Configuration](#configuration)
- [Safety model](#safety-model)
- [Architecture](#architecture)

---

## Install

Requires Python ≥ 3.11.

```bash
# with uv (recommended)
uv venv && uv pip install -e .

# or plain pip
pip install -e .
```

This installs the `trading-mcp` console command (it speaks MCP over stdio).

Smoke-test it:

```bash
trading-mcp            # starts the server (Ctrl-C to stop) — no output is normal; logs go to a file
pytest                 # after: pip install -e ".[dev]"
```

---

## Use with Claude

The server communicates over **stdio**, so any MCP client launches it as a subprocess.

### Claude Desktop

Edit your MCP config file:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```jsonc
{
  "mcpServers": {
    "trading-mcp": {
      "command": "trading-mcp"
    }
  }
}
```

If `trading-mcp` isn't on Claude's PATH, use the venv's absolute path instead:

```jsonc
{
  "mcpServers": {
    "trading-mcp": {
      "command": "/abs/path/to/trading-mcp/.venv/bin/trading-mcp"
    }
  }
}
```

Or run it as a module (no console script needed):

```jsonc
{
  "mcpServers": {
    "trading-mcp": {
      "command": "/abs/path/to/.venv/bin/python",
      "args": ["-m", "mcp_trading"]
    }
  }
}
```

Restart Claude Desktop — you'll see the 🔌 tools appear. Try: *"Use trading-mcp to analyze BTC gamma
exposure and the vol surface, then summarize the regime."*

### Claude Code (CLI)

```bash
# from anywhere, register the installed command
claude mcp add trading-mcp -- trading-mcp

# or pin to a specific venv / module form
claude mcp add trading-mcp -- /abs/path/to/.venv/bin/python -m mcp_trading

# with an API key for the position tools (see below)
claude mcp add trading-mcp --env BYBIT_API_KEY=xxx --env BYBIT_API_SECRET=yyy -- trading-mcp

claude mcp list          # verify it's connected
```

Then in a Claude Code session: *"call get_gex_analysis for ETH and explain the key levels."*

---

## Keep the session rolling

**The single biggest win: don't treat each query as one-shot. Keep one long-lived chat and let market data
accumulate in it over time.** A single snapshot tells the model where the market *is*; a session that has
seen several snapshots tells it where the market is *going* — and that's where the analysis gets sharp.

Why it works:

- **Deltas beat levels.** "IV is 93%" is noise; "ETH IV went +6.6 pts into an up-move while GEX short
  gamma halved" is a tradable signal. The model can only compute that second sentence if the earlier
  snapshot is still in context. See the `2026-06-08` example memos — they're *entirely* a diff against the
  `2026-06-07` snapshot taken ~11h earlier.
- **Positions get tracked in time.** Re-run the position tools (or paste your book) into the same session
  and the agent follows each leg across snapshots — PnL drift, greeks decay, whether the original thesis
  still holds, when premium has bled enough to exit. It remembers what it recommended and grades it.
- **Theses carry forward.** The trade ideas, strikes, and risk levels from the first memo become the
  reference frame for the next one ("the ETH put-spread thesis is *stronger* now — wider premium, less
  short gamma, price lifted off support"), instead of starting cold every time.

Practical loop:

1. Start a memo: *"pull BTC + ETH flow, sentiment, technicals, IV-RV and write a market memo."*
2. Hours/days later, **in the same chat**: *"re-pull everything and give me a delta update vs the last
   snapshot — what changed, and does it change the trade?"*
3. With an API key add: *"also pull my positions and track them against the thesis."*

A real multi-day position-tracking history (Claude following a book across snapshots) is published here:

**→ https://claude.ai/share/cdb4169c-2656-42b9-99e1-6b6b23469ace**

---

## Example outputs

The [`examples/`](examples/) folder holds real, unedited memos generated through this server:

| File | What it is |
|------|------------|
| [`claude_market_analysis_2026-06-07.md`](examples/claude_market_analysis_2026-06-07.md) | Full BTC/ETH options memo — snapshot, IV-RV edge, GEX structure, ranked trade ideas |
| [`codex_market_analysis_2026-06-07.md`](examples/codex_market_analysis_2026-06-07.md) | Same day via Codex — straddle/strangle picks with strikes, breakevens, allocation |
| [`claude_market_analysis_2026-06-08.md`](examples/claude_market_analysis_2026-06-08.md) | **Delta update** ~11h later — a `Then → Now → Δ` table and what the shifts mean for the thesis |
| [`codex_market_analysis_2026-06-08.md`](examples/codex_market_analysis_2026-06-08.md) | Codex delta update — re-ranked trades, updated allocation, risk controls |

The `06-08` files only exist *because* the `06-07` snapshot was still in the session — that's the rolling
workflow above, captured on disk.

---

## API key setup (optional)

**Most tools need no credentials** — GEX, vanna, skew, flow, vol surface, indicators, klines, funding,
OI, options chain, IV-RV, and all strategy-analysis tools use Bybit **public** market data.

Only the **two user-position tools** (`get_user_options_positions`, `get_user_all_positions`) require a
Bybit API key. A **read-only** key is enough and recommended.

Provide the key by env var (`BYBIT_API_KEY`, `BYBIT_API_SECRET`) any of these ways:

```bash
# 1) .env file (copy the template, fill in)
cp .env.example .env

# 2) inline in the Claude Desktop config
#    "trading-mcp": { "command": "trading-mcp",
#      "env": { "BYBIT_API_KEY": "xxx", "BYBIT_API_SECRET": "yyy" } }

# 3) Claude Code flags
claude mcp add trading-mcp --env BYBIT_API_KEY=xxx --env BYBIT_API_SECRET=yyy -- trading-mcp
```

Without a key the position tools return a structured error; everything else works.

---

## The 22 tools

Every tool returns a uniform envelope — `{ "success": bool, "data": …, "timestamp": … }` (or a
tool-specific structured object). Defaults shown in `()`.

### Options flow (5)
| Tool | Params | Returns |
|------|--------|---------|
| `get_gex_analysis` | `base_coin`(BTC), `min_oi`(1.0) | Gamma-exposure profile: net GEX, gamma walls, flip level, dealer-positioning market impact |
| `get_vanna_analysis` | `base_coin`(BTC), `price_move`(0.05) | Vanna exposure and the implied-vol impact of a given % price move |
| `get_flow_analysis` | `base_coin`(BTC) | Options flow: volume, put/call ratios, unusual-activity flags |
| `get_skew_analysis` | `base_coin`(BTC) | Volatility skew + term structure across strikes and expiries |
| `get_vol_surface_metrics` | `base_coin`(BTC) | Surface diagnostics: 25Δ risk-reversal, 10Δ skew, vol-of-vol, variance-risk premium |

### Technical analysis (1)
| Tool | Params | Returns |
|------|--------|---------|
| `get_technical_indicators` | `symbol`, `interval`(1h), `hours_back`(720) | EMA stack, RSI, MACD, ATR, Bollinger, ADX, Hurst exponent, Z-score |

### Market data (2)
| Tool | Params | Returns |
|------|--------|---------|
| `get_historical_data` | `symbol`, `interval`(1h), `hours_back`(720) | Kline count, latest price, last 10 OHLCV candles |
| `get_options_chain` | `base_coin`(BTC), `min_oi`(1.0) | Live options chain, OI-filtered, with a sample slice |

### Sentiment & positioning (3)
| Tool | Params | Returns |
|------|--------|---------|
| `get_market_sentiment_analysis` | `symbol`(BTCUSDT) | Long/short ratios, positioning bias, sentiment extremes |
| `get_open_interest_analysis` | `symbol`(BTCUSDT) | Open-interest level + trend |
| `get_funding_rate_analysis` | `symbol`(BTCUSDT) | Funding rate, carry cost, funding extremes |

### Portfolio (2)
| Tool | Params | Returns |
|------|--------|---------|
| `analyze_portfolio_greeks` | `portfolio_data` | Aggregate Δ/Γ/Θ/Vega + risk metrics for a set of option positions |
| `run_scenario_analysis` | `portfolio_data`, `scenarios` | Portfolio PnL across supplied price/vol scenarios |

### Vol selling (2)
| Tool | Params | Returns |
|------|--------|---------|
| `get_iv_rv_spread` | `base_coin`(BTC), `rv_window`(30) | ATM implied vol vs Garman-Klass realized vol spread — the vol-selling edge metric |
| `get_covered_call_signal` | `base_coin`(BTC), `target_delta`(0.10), `iv_rv_threshold`(10.0), `max_dte`(14) | Covered-call go/no-go: IV-RV check, vol regime, term structure, skew, recommended OTM strike |

### Strategy analysis (4)
| Tool | Params | Returns |
|------|--------|---------|
| `analyze_straddles` | `base_coin`(BTC), `min_oi`(10.0) | Straddle candidates ranked by profitability |
| `analyze_strangles` | `base_coin`(BTC), `min_oi`(10.0) | Strangle optimization |
| `analyze_spreads` | `base_coin`(BTC), `min_oi`(10.0), `spread_types`([call_spread,put_spread]) | Vertical call/put spread analysis |
| `analyze_portfolio_strategies` | `portfolio_positions` | Classifies existing multi-leg strategies in a portfolio (legs, confidence, net cost, breakevens) |

### User positions (2) — *API-key gated*
| Tool | Params | Returns |
|------|--------|---------|
| `get_user_options_positions` | `base_coin`(BTC, or `all`), `position_type`(option) | Live option positions + total unrealised PnL |
| `get_user_all_positions` | `base_coin`(BTC), `position_type`(option/linear/inverse/all) | All positions, per-category breakdown + summary |

### Meta (1)
| Tool | Params | Returns |
|------|--------|---------|
| `get_server_info` | — | Server name, version, tool count, categories |

---

## Bonus: the research prompt

The server also ships one MCP **prompt**, `quant_research_prompt(asset)`, that primes Claude with a
senior-quant options-research workflow — it tells the model which tools to call and how to structure a
market memo (snapshot → sentiment/flow → microstructure → strategy proposals → risk checklist). In Claude
Desktop it appears in the prompt picker; just pass an asset like `BTC`.

---

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `BYBIT_API_KEY` / `BYBIT_API_SECRET` | — | Only for the two user-position tools (read-only key recommended) |
| `MCP_LOG_FILE` | `/tmp/mcp-trading.log` | Where the server logs (never stdout — stdio is the JSON-RPC channel) |
| `DEBUG_MCP` | unset | Set to `1` for DEBUG-level logs |

---

## Safety model

- **Uniform envelope** — every tool returns structured `{success, data, timestamp}`; failures are never free text.
- **Read-first** — the analytics surface has no side effects; nothing places or modifies orders.
- **Key-gated** — only the position tools touch authenticated endpoints; an unconfigured agent physically can't read your book, let alone move money. Use a **read-only** key.
- **Logs off the wire** — MCP uses stdio for JSON-RPC, so all logging is file-only by design.

---

## Architecture

```
mcp_trading/            thin MCP facade — server.py = 22 @mcp.tool wrappers + 1 prompt
  ├─ orchestrator.py    routes tool calls to the libs; holds the Bybit client + vol analyzer
  ├─ options_lib/       GEX · vanna · skew · flow · vol surface · strategy classification · pricing
  ├─ indicators_lib/    technicals + sentiment
  ├─ portfolio_lib/     portfolio engine · greeks · scenario analysis
  └─ bybit_api/         exchange client (klines, options chain, funding, OI, positions)
```

The facade holds **no business logic** — it validates inputs (Pydantic models) and delegates. That's why
the agent and the bots compute identical numbers from identical code.

## License

MIT — see [LICENSE](LICENSE).
