"""
MILP model for RPML optimization using OR-Tools with HiGHS backend.

Implements the model from Rios-Solis et al. (2017) for optimal debt repayment.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from ortools.linear_solver import pywraplp

from .data_loader import PROHIBITED_VALUE, RiosSolisInstance


@dataclass
class RPMLSolution:
    """Solution to the RPML optimization problem."""
    payments: np.ndarray  # shape (n, T) - X[j,t]
    balances: np.ndarray  # shape (n, T) - B[j,t]
    savings: np.ndarray  # shape (T,) - S[t]
    active_loans: np.ndarray  # shape (n, T) - Z[j,t]
    objective_value: float
    solve_time: float
    gap: float
    status: str


DEFAULT_SOLVER = "HIGHS"
FALLBACK_SOLVER = "SCIP"


class RPMLModel:
    """
    MILP model for Repayment Planning for Multiple Loans.
    
    Variables:
        X[j,t] >= 0: Payment for loan j in month t
        B[j,t] >= 0: Balance of loan j at end of month t
        Z[j,t] in {0,1}: Binary indicator if loan j is active in month t
        S[t] >= 0: Savings at end of month t
        C[j,t] >= 0: Penalty for underpayment
        P[j,t] >= 0: Penalty for overpayment
        Y[j,t] in {0,1}: Binary indicator for overpayment
    
    Objective: Minimize sum of all payments sum_{j,t} X[j,t]
    """
    
    def __init__(
        self,
        instance: RiosSolisInstance,
        time_limit_seconds: Optional[int] = None,
        solver_name: str = DEFAULT_SOLVER,
    ):
        """
        Initialize RPML model.
        
        Args:
            instance: Problem instance data
            time_limit_seconds: Maximum solve time (None = no limit)
            solver_name: OR-Tools MIP backend name (e.g. HIGHS, SCIP)
        """
        self.instance = instance
        self.time_limit = time_limit_seconds
        self.solver_name = solver_name.upper()
        
        # Big-M constant for big-M constraints
        # 1e12 is too large and causes severe numerical instability (solver hangs/leakage).
        # We compute a safe upper bound per loan later, but keep a reasonable default M.
        self.M = 1e7
        
        # Calculate per-loan Big-M to tighten constraints and improve numerical stability
        self.M_j = []
        for j in range(instance.n):
            max_rate = float(np.max(instance.interest_rates[j]))
            m_val = float(instance.principals[j]) * (1.0 + max_rate)**instance.T
            # Cap at 1e9 to avoid numerical issues, but ensure it's at least 1e6
            self.M_j.append(max(1e6, min(1e9, m_val * 2.0)))
        
        # Solver initialization
        self.solver = pywraplp.Solver.CreateSolver(self.solver_name)
        if self.solver is None:
            raise RuntimeError(f"{self.solver_name} solver not available in OR-Tools build.")
        if hasattr(self.solver, 'SuppressOutput'):
            self.solver.SuppressOutput()
        if time_limit_seconds is not None:
            self.solver.SetTimeLimit(time_limit_seconds * 1000)  # Convert to milliseconds
            
        # Use solver-specific relative gap parameter. 0.1% gap gives near-optimal
        # results without excessive solve time for typical instances.
        if self.solver_name == "SCIP":
            self.solver.SetSolverSpecificParametersAsString("limits/gap = 0.01")
        else:
            self.solver.SetSolverSpecificParametersAsString("mip_rel_gap=0.01")
        
        # Variables will be created in build_model()
        self.X = None  # Payments
        self.B = None  # Balances
        self.Z = None  # Active loans (binary)
        self.S = None  # Savings
        self.C = None  # Underpayment penalties (added to balance)
        self.P = None  # Prepayment penalties (added to cost)
        self.Y = None  # Prepayment indicator (binary)

    def _credit_card_range(self) -> range:
        start = self.instance.n_cars + self.instance.n_houses
        stop = start + self.instance.n_credit_cards
        return range(start, stop)

    def _is_credit_card(self, loan_idx: int) -> bool:
        return loan_idx in self._credit_card_range()
    
    def build_model(self):
        """Build the complete MILP model."""
        n = self.instance.n
        T = self.instance.T
        
        # Create variables
        self.X = {}
        self.B = {}
        self.Z = {}
        self.S = {}
        self.C = {}
        self.P = {}
        self.Y = {}
        
        for j in range(n):
            for t in range(T):
                self.X[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'X_{j}_{t}')
                self.B[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'B_{j}_{t}')
                self.Z[j, t] = self.solver.IntVar(0, 1, f'Z_{j}_{t}')
                self.C[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'C_{j}_{t}')
                self.P[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'P_{j}_{t}')
                self.Y[j, t] = self.solver.IntVar(0, 1, f'Y_{j}_{t}')
        
        for t in range(T):
            self.S[t] = self.solver.NumVar(0, self.solver.infinity(), f'S_{t}')
        
        # Objective: minimize total payments. Both C and P are carried inside the
        # loan balance, so future X payments absorb their effect.
        objective = self.solver.Objective()
        for j in range(n):
            for t in range(T):
                objective.SetCoefficient(self.X[j, t], 1.0)
        objective.SetMinimization()
        
        # Constraint 1: Budget constraints
        # sum_j(X[j,t]) + S[t] <= monthly_income[t] + S[t-1]
        # Note: C and P are penalties paid, but they come from the loan balance, not budget
        budget_0 = self.solver.Constraint(-self.solver.infinity(), self.instance.monthly_income[0])
        for j in range(n):
            budget_0.SetCoefficient(self.X[j, 0], 1.0)
        budget_0.SetCoefficient(self.S[0], 1.0)
        
        for t in range(1, T):
            budget = self.solver.Constraint(-self.solver.infinity(), self.instance.monthly_income[t])
            for j in range(n):
                budget.SetCoefficient(self.X[j, t], 1.0)
            budget.SetCoefficient(self.S[t], 1.0)
            budget.SetCoefficient(self.S[t-1], -1.0)
        
        # Constraint 2: Balance dynamics and initial conditions
        for j in range(n):
            r_j = self.instance.release_time[j]
            
            # Force inactivity before release
            for t in range(r_j):
                inactive = self.solver.Constraint(0, 0)
                inactive.SetCoefficient(self.Z[j, t], 1.0)
                inactive_balance = self.solver.Constraint(0, 0)
                inactive_balance.SetCoefficient(self.B[j, t], 1.0)
                inactive_payment = self.solver.Constraint(0, 0)
                inactive_payment.SetCoefficient(self.X[j, t], 1.0)
                inactive_c = self.solver.Constraint(0, 0)
                inactive_c.SetCoefficient(self.C[j, t], 1.0)
                inactive_p = self.solver.Constraint(0, 0)
                inactive_p.SetCoefficient(self.P[j, t], 1.0)
                inactive_y = self.solver.Constraint(0, 0)
                inactive_y.SetCoefficient(self.Y[j, t], 1.0)
            
            # Balance at release month (article Eq. 7): B[j,r_j] = principal[j]
            # Payment/penalties are not modeled in this month in the article
            # balance equation, so we keep X/C/P/Y fixed to zero at release.
            init_balance_value = self.instance.principals[j]
            init_balance = self.solver.Constraint(init_balance_value, init_balance_value)
            init_balance.SetCoefficient(self.B[j, r_j], 1.0)
            
            zero_x_release = self.solver.Constraint(0, 0)
            zero_x_release.SetCoefficient(self.X[j, r_j], 1.0)
            zero_c_release = self.solver.Constraint(0, 0)
            zero_c_release.SetCoefficient(self.C[j, r_j], 1.0)
            zero_p_release = self.solver.Constraint(0, 0)
            zero_p_release.SetCoefficient(self.P[j, r_j], 1.0)
            zero_y_release = self.solver.Constraint(0, 0)
            zero_y_release.SetCoefficient(self.Y[j, r_j], 1.0)
            
            # Balance dynamics for t > r_j:
            # B[j,t] = B[j,t-1]*(1+i[j,t]) - X[j,t] + C[j,t] + P[j,t]
            for t in range(r_j + 1, T):
                i_jt = self.instance.interest_rates[j, t]
                balance_eq = self.solver.Constraint(0, 0)
                balance_eq.SetCoefficient(self.B[j, t], 1.0)
                balance_eq.SetCoefficient(self.B[j, t-1], -(1.0 + i_jt))
                balance_eq.SetCoefficient(self.X[j, t], 1.0)
                balance_eq.SetCoefficient(self.C[j, t], -1.0)
                balance_eq.SetCoefficient(self.P[j, t], -1.0)
                
                # Cap payment by outstanding balance with interest
                max_payment = self.solver.Constraint(-self.solver.infinity(), 0)
                max_payment.SetCoefficient(self.X[j, t], 1.0)
                max_payment.SetCoefficient(self.B[j, t-1], -(1.0 + i_jt))
        
        # Constraint 3: Loan activity (big-M)
        # B[j,t] <= M * Z[j,t]
        # B[j,t-1] * (1+i[j,t]) <= M * Z[j,t]  (article Eq. 9 analogue)
        for j in range(n):
            M_j = self.M_j[j]
            for t in range(self.instance.T):
                activity = self.solver.Constraint(-self.solver.infinity(), 0)
                activity.SetCoefficient(self.B[j, t], 1.0)
                activity.SetCoefficient(self.Z[j, t], -M_j)
                # Payments only when active
                active_pay = self.solver.Constraint(-self.solver.infinity(), 0)
                active_pay.SetCoefficient(self.X[j, t], 1.0)
                active_pay.SetCoefficient(self.Z[j, t], -M_j)

                # If debt exists at the beginning of month t, loan must be active.
                if t > self.instance.release_time[j]:
                    begins_with_balance = self.solver.Constraint(-self.solver.infinity(), 0)
                    begins_with_balance.SetCoefficient(
                        self.B[j, t - 1],
                        1.0 + self.instance.interest_rates[j, t],
                    )
                    begins_with_balance.SetCoefficient(self.Z[j, t], -M_j)

                # Monotonicity of activity: once inactive stays inactive
                if t > self.instance.release_time[j]:
                    monotone = self.solver.Constraint(0, self.solver.infinity())
                    monotone.SetCoefficient(self.Z[j, t-1], 1.0)
                    monotone.SetCoefficient(self.Z[j, t], -1.0)
        
        # Constraint 4: Underpayment penalty.
        # Non-credit-card loans use contractual fixed_payment E_j^t.
        # Credit cards use pm_j * B[j,t-1] * (1 + i[j,t]).
        for j in range(n):
            r_j = self.instance.release_time[j]
            
            for t in range(r_j + 1, self.instance.T):
                h_jt = self.instance.default_rates[j, t]
                penalty_mult = 1.0 + h_jt

                underpayment = self.solver.Constraint(0, self.solver.infinity())
                underpayment.SetCoefficient(self.C[j, t], 1.0)
                underpayment.SetCoefficient(self.X[j, t], penalty_mult)

                if self._is_credit_card(j):
                    min_pct = self.instance.min_payment_pct[j]
                    i_jt = self.instance.interest_rates[j, t]
                    underpayment.SetCoefficient(
                        self.B[j, t-1],
                        -penalty_mult * min_pct * (1.0 + i_jt),
                    )
                else:
                    contractual_payment = float(self.instance.fixed_payment[j])
                    # If the loan is paid off this month (B[j,t] == 0), we don't need to pay the full contractual amount.
                    # Z[j,t+1] is 1 if the loan carries a balance into the next month.
                    # For t == T-1, the loan must be paid off (B[j,T-1] == 0), so no penalty applies.
                    if t < self.instance.T - 1:
                        underpayment.SetCoefficient(
                            self.Z[j, t+1],
                            -penalty_mult * contractual_payment,
                        )
                    else:
                        # In the final month, it must be paid off, so no minimum fixed payment is enforced
                        pass

        # Constraint 5: Prepayment penalty / overpayment prohibition.
        # E_j^t is represented in the dataset by fixed_payment for non-credit-card
        # loans; for credit cards the field is set to a huge sentinel value, so the
        # constraint becomes inactive.
        for j in range(n):
            r_j = self.instance.release_time[j]
            contractual_payment = float(self.instance.fixed_payment[j])
            penalty = float(self.instance.prepay_penalty[j])

            for t in range(r_j + 1, self.instance.T):
                if penalty >= PROHIBITED_VALUE * 0.1:
                    no_overpay = self.solver.Constraint(-self.solver.infinity(), 0)
                    no_overpay.SetCoefficient(self.X[j, t], 1.0)
                    no_overpay.SetCoefficient(self.Z[j, t], -contractual_payment)

                    zero_p = self.solver.Constraint(0, 0)
                    zero_p.SetCoefficient(self.P[j, t], 1.0)
                    zero_y = self.solver.Constraint(0, 0)
                    zero_y.SetCoefficient(self.Y[j, t], 1.0)
                    continue

                trigger_overpay = self.solver.Constraint(-self.solver.infinity(), 0)
                trigger_overpay.SetCoefficient(self.X[j, t], 1.0)
                trigger_overpay.SetCoefficient(self.Z[j, t], -contractual_payment)
                trigger_overpay.SetCoefficient(self.Y[j, t], -self.M_j[j])

                y_only_when_active = self.solver.Constraint(-self.solver.infinity(), 0)
                y_only_when_active.SetCoefficient(self.Y[j, t], 1.0)
                y_only_when_active.SetCoefficient(self.Z[j, t], -1.0)

                prepayment_penalty = self.solver.Constraint(0, 0)
                prepayment_penalty.SetCoefficient(self.P[j, t], 1.0)
                prepayment_penalty.SetCoefficient(self.Y[j, t], -penalty)
        
        # Constraint 7: Final balance must be zero
        # B[j, T-1] = 0 for all j
        for j in range(n):
            final_balance = self.solver.Constraint(0, 0)
            final_balance.SetCoefficient(self.B[j, T-1], 1.0)

        # Constraint 8: Financial parity analogue to article Eq. (6), with the
        # implementation time-index convention where interest starts from r_j+1.
        for j in range(n):
            r_j = int(self.instance.release_time[j])
            rhs = -float(self.instance.principals[j]) * float(
                np.prod(1.0 + self.instance.interest_rates[j, r_j + 1:T])
            )
            parity = self.solver.Constraint(rhs, rhs)
            for t in range(r_j + 1, T):
                coef = float(np.prod(1.0 + self.instance.interest_rates[j, t + 1:T]))
                parity.SetCoefficient(self.X[j, t], -coef)
                parity.SetCoefficient(self.C[j, t], coef)
                parity.SetCoefficient(self.P[j, t], coef)
    
    def solve(self) -> RPMLSolution:
        """
        Solve the MILP model.
        
        Returns:
            RPMLSolution object with results
        """
        if self.X is None:
            self.build_model()
        
        import time
        start_time = time.time()
        status = self.solver.Solve()
        solve_time = time.time() - start_time

        n = self.instance.n
        T = self.instance.T
        status_map = {
            pywraplp.Solver.OPTIMAL: "OPTIMAL",
            pywraplp.Solver.FEASIBLE: "FEASIBLE",
            pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
            pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
            pywraplp.Solver.ABNORMAL: "ABNORMAL",
            pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
        }
        status_str = status_map.get(status, f"UNKNOWN_{status}")

        if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return RPMLSolution(
                payments=np.zeros((n, T)),
                balances=np.zeros((n, T)),
                savings=np.zeros(T),
                active_loans=np.zeros((n, T)),
                objective_value=float("inf"),
                solve_time=solve_time,
                gap=0.0,
                status=status_str,
            )

        payments = np.zeros((n, T))
        balances = np.zeros((n, T))
        savings = np.zeros(T)
        active_loans = np.zeros((n, T))
        for j in range(n):
            for t in range(T):
                payments[j, t] = self.X[j, t].solution_value()
                balances[j, t] = self.B[j, t].solution_value()
                active_loans[j, t] = self.Z[j, t].solution_value()
        for t in range(T):
            savings[t] = self.S[t].solution_value()
        obj_value = self.solver.Objective().Value()

        gap = 0.0
        if hasattr(self.solver, 'GetBestObjectiveBound'):
            try:
                best_bound = self.solver.GetBestObjectiveBound()
                if obj_value > 0:
                    gap = abs(best_bound - obj_value) / obj_value * 100
            except Exception:
                pass

        return RPMLSolution(
            payments=payments,
            balances=balances,
            savings=savings,
            active_loans=active_loans,
            objective_value=obj_value,
            solve_time=solve_time,
            gap=gap,
            status=status_str,
        )


def solve_rpml(
    instance: RiosSolisInstance,
    time_limit_seconds: Optional[int] = None,
    solver_name: str = DEFAULT_SOLVER,
) -> RPMLSolution:
    """
    Convenience function to solve RPML instance.
    
    Args:
        instance: Problem instance
        time_limit_seconds: Maximum solve time
        solver_name: OR-Tools MIP backend name
    
    Returns:
        RPMLSolution with results
    """
    model = RPMLModel(instance, time_limit_seconds, solver_name=solver_name)
    return model.solve()

