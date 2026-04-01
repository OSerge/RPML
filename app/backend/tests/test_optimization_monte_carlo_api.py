def test_sync_optimization_mc_defaults_contract(client, auth_headers, seeded_debts, monkeypatch):
    captured = {}
    summary = {
        "n_scenarios": 16,
        "feasible_scenarios": 12,
        "infeasible_rate": 0.25,
        "mean_total_cost": 321.0,
        "median_total_cost": 300.0,
        "p90_total_cost": 450.0,
        "mean_solve_time": 0.5,
        "p90_solve_time": 0.8,
    }

    def fake_mc(instance, *, ru_mode):
        captured["ru_mode"] = ru_mode
        return summary

    monkeypatch.setattr(
        "server.application.use_cases.run_optimization_sync._build_monte_carlo_summary",
        fake_mc,
    )
    res = client.post(
        "/api/v1/optimization/run",
        headers=auth_headers,
        json={"horizon_months": 12, "mc_income": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert captured["ru_mode"] is True
    assert body["ru_mode"] is True
    assert body["mc_income"] is True
    assert body["mc_summary"] == summary
