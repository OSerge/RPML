from __future__ import annotations

import json
from dataclasses import dataclass

import gradio as gr
import httpx


@dataclass
class ApiSession:
    base_url: str
    token: str = ""
    last_task_id: str = ""
    last_plan_id: str = ""
    last_debt_id: str = ""

    @property
    def auth_headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}


def _pretty(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _json_or_text(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text}


def _loan_type_hint_text(loan_type: str) -> str:
    common = (
        "Для API CRUD схема единая для всех типов: специальных обязательных полей по типу нет. "
        "Но для оптимизации все числовые поля кредита должны быть заполнены (не null)."
    )
    type_notes = {
        "car_loan": "Тип: car_loan. Обычно фиксированный платёж и низкий prepay_penalty.",
        "house_loan": "Тип: house_loan. Обычно длинный срок и крупный principal.",
        "credit_card": "Тип: credit_card. Часто выше ставки interest/default.",
        "bank_loan": "Тип: bank_loan. Универсальный тип для прочих займов.",
    }
    return f"{type_notes.get(loan_type, 'Тип кредита не выбран.')} {common}"


def _debt_form_values_from_body(body: object) -> tuple:
    if not isinstance(body, dict):
        return ("", "loan_from_gradio", "bank_loan", 100000.0, 5000.0, 0.1, 0.0, 0.01, 0.05, 1000.0, 0)
    return (
        str(body.get("id", "")),
        str(body.get("name", "loan_from_gradio")),
        str(body.get("loan_type", "bank_loan")),
        float(body.get("principal", 100000.0) or 0.0),
        float(body.get("fixed_payment", 5000.0) or 0.0),
        float(body.get("min_payment_pct", 0.1) or 0.0),
        float(body.get("prepay_penalty", 0.0) or 0.0),
        float(body.get("interest_rate_monthly", 0.01) or 0.0),
        float(body.get("default_rate_monthly", 0.05) or 0.0),
        float(body.get("stipulated_amount", 1000.0) or 0.0),
        int(body.get("release_time", 0) or 0),
    )


def _build_sync_kpi(body: object) -> dict:
    if not isinstance(body, dict):
        return {"error": "unexpected response payload"}
    kpi = {
        "status": body.get("status"),
        "base_total_cost": body.get("total_cost"),
        "ru_mode": body.get("ru_mode"),
        "mc_income": body.get("mc_income"),
        "has_mc_summary": body.get("mc_summary") is not None,
    }
    mc_summary = body.get("mc_summary")
    base_total_cost = body.get("total_cost")
    if isinstance(mc_summary, dict):
        mean_cost = mc_summary.get("mean_total_cost")
        p90_cost = mc_summary.get("p90_total_cost")
        kpi["mc_mean_total_cost"] = mean_cost
        kpi["mc_median_total_cost"] = mc_summary.get("median_total_cost")
        kpi["mc_p90_total_cost"] = p90_cost
        kpi["mc_feasible_scenarios"] = mc_summary.get("feasible_scenarios")
        kpi["mc_n_scenarios"] = mc_summary.get("n_scenarios")
        kpi["mc_infeasible_rate"] = mc_summary.get("infeasible_rate")
        if isinstance(base_total_cost, (int, float)):
            if isinstance(mean_cost, (int, float)):
                kpi["delta_mean_vs_base_abs"] = float(mean_cost) - float(base_total_cost)
            if isinstance(p90_cost, (int, float)):
                kpi["delta_p90_vs_base_abs"] = float(p90_cost) - float(base_total_cost)
    return kpi


def login(base_url: str, email: str, password: str, state: ApiSession):
    normalized = _normalize_base_url(base_url)
    payload = {"email": email, "password": password}
    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{normalized}/api/v1/auth/login", json=payload)
    body = _json_or_text(response)
    if response.status_code == 200 and "access_token" in body:
        state.base_url = normalized
        state.token = body["access_token"]
        return state, "Успешный вход", _pretty(body)
    return state, f"Ошибка входа: HTTP {response.status_code}", _pretty(body)


def run_sync(base_url: str, horizon_months: int, ru_mode: bool, mc_income: bool, state: ApiSession):
    normalized = _normalize_base_url(base_url)
    payload = {
        "horizon_months": int(horizon_months),
        "ru_mode": bool(ru_mode),
        "mc_income": bool(mc_income),
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            f"{normalized}/api/v1/optimization/run",
            headers=state.auth_headers,
            json=payload,
        )
    body = _json_or_text(response)
    if response.status_code == 200:
        kpi = _build_sync_kpi(body)
        return _pretty(kpi), _pretty(body)
    return _pretty({"http_status": response.status_code}), _pretty(body)


def create_async_task(
    base_url: str,
    horizon_months: int,
    ru_mode: bool,
    mc_income: bool,
    state: ApiSession,
):
    normalized = _normalize_base_url(base_url)
    payload = {
        "horizon_months": int(horizon_months),
        "ru_mode": bool(ru_mode),
        "mc_income": bool(mc_income),
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{normalized}/api/v1/optimization/tasks",
            headers=state.auth_headers,
            json=payload,
        )
    body = _json_or_text(response)
    if response.status_code == 202 and body.get("task_id"):
        state.last_task_id = body["task_id"]
    return state, _pretty(body)


def get_task_status(base_url: str, task_id: str, state: ApiSession):
    normalized = _normalize_base_url(base_url)
    effective_task_id = task_id.strip() or state.last_task_id
    if not effective_task_id:
        return state, _pretty({"error": "task_id is required"})
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{normalized}/api/v1/optimization/tasks/{effective_task_id}",
            headers=state.auth_headers,
        )
    body = _json_or_text(response)
    if response.status_code == 200 and body.get("plan_id"):
        state.last_plan_id = body["plan_id"]
    return state, _pretty(body)


def get_plan(base_url: str, plan_id: str, state: ApiSession):
    normalized = _normalize_base_url(base_url)
    effective_plan_id = plan_id.strip() or state.last_plan_id
    if not effective_plan_id:
        return _pretty({"error": "plan_id is required"})
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{normalized}/api/v1/optimization/plans/{effective_plan_id}",
            headers=state.auth_headers,
        )
    return _pretty({"http_status": response.status_code, "body": _json_or_text(response)})


def get_loan_types(base_url: str, state: ApiSession):
    normalized = _normalize_base_url(base_url)
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{normalized}/api/v1/debts/loan-types")
    return _pretty({"http_status": response.status_code, "body": _json_or_text(response)})


def list_debts(base_url: str, state: ApiSession):
    normalized = _normalize_base_url(base_url)
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{normalized}/api/v1/debts",
            headers=state.auth_headers,
        )
    body = _json_or_text(response)
    debt_form_values = ("", "loan_from_gradio", "bank_loan", 100000.0, 5000.0, 0.1, 0.0, 0.01, 0.05, 1000.0, 0)
    if response.status_code == 200 and isinstance(body, list) and body:
        first = body[0]
        first_id = first.get("id")
        if first_id is not None:
            state.last_debt_id = str(first_id)
        debt_form_values = _debt_form_values_from_body(first)
    return (
        state,
        _pretty({"http_status": response.status_code, "body": body}),
        *debt_form_values,
        _loan_type_hint_text(debt_form_values[2]),
    )


def create_debt(
    base_url: str,
    name: str,
    loan_type: str,
    principal: float,
    fixed_payment: float,
    min_payment_pct: float,
    prepay_penalty: float,
    interest_rate_monthly: float,
    default_rate_monthly: float,
    stipulated_amount: float,
    release_time: int,
    state: ApiSession,
):
    normalized = _normalize_base_url(base_url)
    payload = {
        "name": name,
        "loan_type": loan_type,
        "principal": float(principal),
        "fixed_payment": float(fixed_payment),
        "min_payment_pct": float(min_payment_pct),
        "prepay_penalty": float(prepay_penalty),
        "interest_rate_monthly": float(interest_rate_monthly),
        "default_rate_monthly": float(default_rate_monthly),
        "stipulated_amount": float(stipulated_amount),
        "release_time": int(release_time),
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{normalized}/api/v1/debts",
            headers=state.auth_headers,
            json=payload,
        )
    body = _json_or_text(response)
    debt_form_values = _debt_form_values_from_body(body)
    if response.status_code == 201 and isinstance(body, dict) and body.get("id") is not None:
        state.last_debt_id = str(body["id"])
    return (
        state,
        _pretty({"http_status": response.status_code, "body": body}),
        *debt_form_values,
        _loan_type_hint_text(debt_form_values[2]),
    )


def get_debt(base_url: str, debt_id: str, state: ApiSession):
    normalized = _normalize_base_url(base_url)
    effective_debt_id = debt_id.strip() or state.last_debt_id
    if not effective_debt_id:
        defaults = ("", "loan_from_gradio", "bank_loan", 100000.0, 5000.0, 0.1, 0.0, 0.01, 0.05, 1000.0, 0)
        return state, _pretty({"error": "debt_id is required"}), *defaults, _loan_type_hint_text("bank_loan")
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{normalized}/api/v1/debts/{effective_debt_id}",
            headers=state.auth_headers,
        )
    body = _json_or_text(response)
    debt_form_values = _debt_form_values_from_body(body)
    if response.status_code == 200:
        state.last_debt_id = effective_debt_id
    return (
        state,
        _pretty({"http_status": response.status_code, "body": body}),
        *debt_form_values,
        _loan_type_hint_text(debt_form_values[2]),
    )


def update_debt(
    base_url: str,
    debt_id: str,
    name: str,
    loan_type: str,
    principal: float,
    fixed_payment: float,
    min_payment_pct: float,
    prepay_penalty: float,
    interest_rate_monthly: float,
    default_rate_monthly: float,
    stipulated_amount: float,
    release_time: int,
    state: ApiSession,
):
    normalized = _normalize_base_url(base_url)
    effective_debt_id = debt_id.strip() or state.last_debt_id
    if not effective_debt_id:
        defaults = ("", "loan_from_gradio", "bank_loan", 100000.0, 5000.0, 0.1, 0.0, 0.01, 0.05, 1000.0, 0)
        return state, _pretty({"error": "debt_id is required"}), *defaults, _loan_type_hint_text("bank_loan")
    payload = {
        "name": name,
        "loan_type": loan_type,
        "principal": float(principal),
        "fixed_payment": float(fixed_payment),
        "min_payment_pct": float(min_payment_pct),
        "prepay_penalty": float(prepay_penalty),
        "interest_rate_monthly": float(interest_rate_monthly),
        "default_rate_monthly": float(default_rate_monthly),
        "stipulated_amount": float(stipulated_amount),
        "release_time": int(release_time),
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.patch(
            f"{normalized}/api/v1/debts/{effective_debt_id}",
            headers=state.auth_headers,
            json=payload,
        )
    body = _json_or_text(response)
    debt_form_values = _debt_form_values_from_body(body)
    if response.status_code == 200:
        state.last_debt_id = effective_debt_id
    return (
        state,
        _pretty({"http_status": response.status_code, "body": body}),
        *debt_form_values,
        _loan_type_hint_text(debt_form_values[2]),
    )


def delete_debt(base_url: str, debt_id: str, state: ApiSession):
    normalized = _normalize_base_url(base_url)
    effective_debt_id = debt_id.strip() or state.last_debt_id
    if not effective_debt_id:
        defaults = ("", "loan_from_gradio", "bank_loan", 100000.0, 5000.0, 0.1, 0.0, 0.01, 0.05, 1000.0, 0)
        return state, _pretty({"error": "debt_id is required"}), *defaults, _loan_type_hint_text("bank_loan")
    with httpx.Client(timeout=30.0) as client:
        response = client.delete(
            f"{normalized}/api/v1/debts/{effective_debt_id}",
            headers=state.auth_headers,
        )
    if response.status_code == 204:
        if state.last_debt_id == effective_debt_id:
            state.last_debt_id = ""
        cleared = ("", "loan_from_gradio", "bank_loan", 100000.0, 5000.0, 0.1, 0.0, 0.01, 0.05, 1000.0, 0)
        return state, _pretty({"http_status": 204, "body": None}), *cleared, _loan_type_hint_text("bank_loan")
    body = _json_or_text(response)
    debt_form_values = _debt_form_values_from_body(body)
    return (
        state,
        _pretty({"http_status": response.status_code, "body": body}),
        *debt_form_values,
        _loan_type_hint_text(debt_form_values[2]),
    )


def on_loan_type_change(loan_type: str):
    return _loan_type_hint_text(loan_type)


def build_app() -> gr.Blocks:
    with gr.Blocks(title="RPML API Tester") as app:
        state = gr.State(ApiSession(base_url="http://127.0.0.1:8000"))
        gr.Markdown("## RPML API Tester")

        with gr.Tab("Auth"):
            base_url_auth = gr.Textbox(
                value="http://127.0.0.1:8000",
                label="Base URL",
            )
            email = gr.Textbox(value="demo@example.com", label="Email")
            password = gr.Textbox(value="secret", label="Password", type="password")
            login_btn = gr.Button("Login")
            login_status = gr.Textbox(label="Status", interactive=False)
            login_response = gr.Code(label="Response JSON", language="json")
            login_btn.click(
                login,
                inputs=[base_url_auth, email, password, state],
                outputs=[state, login_status, login_response],
            )

        with gr.Tab("Sync optimization"):
            base_url_sync = gr.Textbox(value="http://127.0.0.1:8000", label="Base URL")
            horizon_sync = gr.Slider(minimum=1, maximum=240, value=12, step=1, label="Horizon months")
            ru_mode_sync = gr.Checkbox(value=True, label="ru_mode")
            mc_income_sync = gr.Checkbox(value=False, label="mc_income")
            sync_btn = gr.Button("Run sync optimization")
            sync_kpi = gr.Code(label="KPI", language="json")
            sync_response = gr.Code(label="Response JSON", language="json")
            sync_btn.click(
                run_sync,
                inputs=[base_url_sync, horizon_sync, ru_mode_sync, mc_income_sync, state],
                outputs=[sync_kpi, sync_response],
            )

        with gr.Tab("Async task"):
            base_url_async = gr.Textbox(value="http://127.0.0.1:8000", label="Base URL")
            horizon_async = gr.Slider(minimum=1, maximum=240, value=24, step=1, label="Horizon months")
            ru_mode_async = gr.Checkbox(value=True, label="ru_mode")
            mc_income_async = gr.Checkbox(value=False, label="mc_income")
            create_task_btn = gr.Button("Create task")
            task_id = gr.Textbox(label="Task ID (optional, uses last created if empty)")
            task_create_response = gr.Code(label="Create response", language="json")
            task_status_btn = gr.Button("Get task status")
            task_status_response = gr.Code(label="Task status response", language="json")
            create_task_btn.click(
                create_async_task,
                inputs=[base_url_async, horizon_async, ru_mode_async, mc_income_async, state],
                outputs=[state, task_create_response],
            )
            task_status_btn.click(
                get_task_status,
                inputs=[base_url_async, task_id, state],
                outputs=[state, task_status_response],
            )

        with gr.Tab("Plan fetch"):
            base_url_plan = gr.Textbox(value="http://127.0.0.1:8000", label="Base URL")
            plan_id = gr.Textbox(label="Plan ID (optional, uses last from task status if empty)")
            plan_btn = gr.Button("Get plan")
            plan_response = gr.Code(label="Plan response", language="json")
            plan_btn.click(
                get_plan,
                inputs=[base_url_plan, plan_id, state],
                outputs=[plan_response],
            )

        with gr.Tab("Debts"):
            base_url_debts = gr.Textbox(value="http://127.0.0.1:8000", label="Base URL")
            with gr.Row():
                loan_types_btn = gr.Button("Get loan types")
                list_debts_btn = gr.Button("List debts")
            debt_id = gr.Textbox(label="Debt ID (optional for get/update/delete)")
            debt_name = gr.Textbox(value="loan_from_gradio", label="name")
            debt_loan_type = gr.Dropdown(
                choices=["car_loan", "house_loan", "credit_card", "bank_loan"],
                value="bank_loan",
                label="loan_type",
            )
            debt_type_hint = gr.Markdown(_loan_type_hint_text("bank_loan"))
            with gr.Row():
                debt_principal = gr.Number(value=100000.0, label="principal")
                debt_fixed_payment = gr.Number(value=5000.0, label="fixed_payment")
                debt_min_payment_pct = gr.Number(value=0.1, label="min_payment_pct")
            with gr.Row():
                debt_prepay_penalty = gr.Number(value=0.0, label="prepay_penalty")
                debt_interest = gr.Number(value=0.01, label="interest_rate_monthly")
                debt_default = gr.Number(value=0.05, label="default_rate_monthly")
            with gr.Row():
                debt_stipulated = gr.Number(value=1000.0, label="stipulated_amount")
                debt_release_time = gr.Number(value=0, precision=0, label="release_time")
            with gr.Row():
                create_debt_btn = gr.Button("Create debt")
                get_debt_btn = gr.Button("Get debt")
                update_debt_btn = gr.Button("Update debt")
                delete_debt_btn = gr.Button("Delete debt")
            debt_response = gr.Code(label="Debts response", language="json")

            loan_types_btn.click(
                get_loan_types,
                inputs=[base_url_debts, state],
                outputs=[debt_response],
            )
            list_debts_btn.click(
                list_debts,
                inputs=[base_url_debts, state],
                outputs=[
                    state,
                    debt_response,
                    debt_id,
                    debt_name,
                    debt_loan_type,
                    debt_principal,
                    debt_fixed_payment,
                    debt_min_payment_pct,
                    debt_prepay_penalty,
                    debt_interest,
                    debt_default,
                    debt_stipulated,
                    debt_release_time,
                    debt_type_hint,
                ],
            )
            create_debt_btn.click(
                create_debt,
                inputs=[
                    base_url_debts,
                    debt_name,
                    debt_loan_type,
                    debt_principal,
                    debt_fixed_payment,
                    debt_min_payment_pct,
                    debt_prepay_penalty,
                    debt_interest,
                    debt_default,
                    debt_stipulated,
                    debt_release_time,
                    state,
                ],
                outputs=[
                    state,
                    debt_response,
                    debt_id,
                    debt_name,
                    debt_loan_type,
                    debt_principal,
                    debt_fixed_payment,
                    debt_min_payment_pct,
                    debt_prepay_penalty,
                    debt_interest,
                    debt_default,
                    debt_stipulated,
                    debt_release_time,
                    debt_type_hint,
                ],
            )
            get_debt_btn.click(
                get_debt,
                inputs=[base_url_debts, debt_id, state],
                outputs=[
                    state,
                    debt_response,
                    debt_id,
                    debt_name,
                    debt_loan_type,
                    debt_principal,
                    debt_fixed_payment,
                    debt_min_payment_pct,
                    debt_prepay_penalty,
                    debt_interest,
                    debt_default,
                    debt_stipulated,
                    debt_release_time,
                    debt_type_hint,
                ],
            )
            update_debt_btn.click(
                update_debt,
                inputs=[
                    base_url_debts,
                    debt_id,
                    debt_name,
                    debt_loan_type,
                    debt_principal,
                    debt_fixed_payment,
                    debt_min_payment_pct,
                    debt_prepay_penalty,
                    debt_interest,
                    debt_default,
                    debt_stipulated,
                    debt_release_time,
                    state,
                ],
                outputs=[
                    state,
                    debt_response,
                    debt_id,
                    debt_name,
                    debt_loan_type,
                    debt_principal,
                    debt_fixed_payment,
                    debt_min_payment_pct,
                    debt_prepay_penalty,
                    debt_interest,
                    debt_default,
                    debt_stipulated,
                    debt_release_time,
                    debt_type_hint,
                ],
            )
            delete_debt_btn.click(
                delete_debt,
                inputs=[base_url_debts, debt_id, state],
                outputs=[
                    state,
                    debt_response,
                    debt_id,
                    debt_name,
                    debt_loan_type,
                    debt_principal,
                    debt_fixed_payment,
                    debt_min_payment_pct,
                    debt_prepay_penalty,
                    debt_interest,
                    debt_default,
                    debt_stipulated,
                    debt_release_time,
                    debt_type_hint,
                ],
            )
            debt_loan_type.change(
                on_loan_type_change,
                inputs=[debt_loan_type],
                outputs=[debt_type_hint],
            )

    return app


if __name__ == "__main__":
    ui = build_app()
    ui.launch(server_name="127.0.0.1", server_port=7860)
