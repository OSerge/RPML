"""Smoke test: RPML package is importable after monorepo relocation."""


def test_rpml_import_and_solver_symbol():
    import rpml

    assert hasattr(rpml, "solve_rpml")
