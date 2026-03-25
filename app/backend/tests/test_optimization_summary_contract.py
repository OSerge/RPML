def test_run_response_contains_summary_contract(client, auth_headers, seeded_debts):
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["horizon_months"] == 12
    assert isinstance(body["balances_matrix"], list)
    comparison = body["baseline_comparison"]
    assert "milp_total_cost" in comparison
    assert "avalanche_total_cost" in comparison
    assert "snowball_total_cost" in comparison
    assert "savings_vs_avalanche_abs" in comparison
    assert "savings_vs_snowball_abs" in comparison
    assert "strategy_results" in comparison
    assert set(comparison["strategy_results"].keys()) == {"milp", "avalanche", "snowball"}
    for strategy_name in ("milp", "avalanche", "snowball"):
        strategy = comparison["strategy_results"][strategy_name]
        assert "total_cost" in strategy
        assert isinstance(strategy["payments_matrix"], list)
        assert isinstance(strategy["balances_matrix"], list)
