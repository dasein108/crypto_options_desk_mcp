"""Standalone smoke tests — prove the bundle imports and the tool surface is intact, no network."""


def test_bundled_libs_import():
    import bybit_api  # noqa: F401
    import indicators_lib  # noqa: F401
    import options_lib  # noqa: F401
    import portfolio_lib  # noqa: F401


def test_server_imports_and_registers_tools():
    # Importing the server wires up the FastMCP app + orchestrator (no network on import).
    from mcp_trading import server

    assert hasattr(server, "mcp"), "FastMCP app missing"
    assert hasattr(server, "orchestrator"), "orchestrator missing"


def test_orchestrator_exposes_analysis_methods():
    from mcp_trading.orchestrator import get_orchestrator

    orch = get_orchestrator()
    for m in ("get_gex_analysis", "get_vanna_analysis", "get_skew_analysis",
              "get_technical_indicators", "analyze_portfolio_greeks", "run_scenario_analysis"):
        assert hasattr(orch, m), m


def test_vendored_volatility_analyzer():
    from mcp_trading.volatility_analyzer import VolatilityAnalyzer  # noqa: F401
