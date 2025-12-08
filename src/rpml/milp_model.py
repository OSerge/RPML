"""
MILP model for RPML optimization using OR-Tools with HiGHS backend.

Implements the model from Rios-Solis et al. (2017) for optimal debt repayment.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from ortools.linear_solver import pywraplp

from .data_loader import RiosSolisInstance


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
    
    def __init__(self, instance: RiosSolisInstance, time_limit_seconds: Optional[int] = None):
        """
        Initialize RPML model.
        
        Args:
            instance: Problem instance data
            time_limit_seconds: Maximum solve time (None = no limit)
        """
        self.instance = instance
        self.time_limit = time_limit_seconds
        
        # Big-M constant for big-M constraints (aligned with dataset prohibition flag)
        self.M = 1e12
        
        # Solver initialization
        self.solver = pywraplp.Solver.CreateSolver('HIGHS')
        if self.solver is None:
            raise RuntimeError("HiGHS solver not available. Install OR-Tools with HiGHS support.")
        
        if time_limit_seconds is not None:
            self.solver.SetTimeLimit(time_limit_seconds * 1000)  # Convert to milliseconds
        
        # Variables will be created in build_model()
        self.X = None  # Payments
        self.B = None  # Balances
        self.Z = None  # Active loans (binary)
        self.S = None  # Savings
        self.C = None  # Underpayment penalties
        self.P = None  # Overpayment penalties
        self.Y = None  # Overpayment indicator (binary)
    
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
        self.O = {}
        
        for j in range(n):
            for t in range(T):
                self.X[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'X_{j}_{t}')
                self.B[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'B_{j}_{t}')
                self.Z[j, t] = self.solver.IntVar(0, 1, f'Z_{j}_{t}')
                self.C[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'C_{j}_{t}')
                self.P[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'P_{j}_{t}')
                self.Y[j, t] = self.solver.IntVar(0, 1, f'Y_{j}_{t}')
                self.O[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'O_{j}_{t}')  # overpayment amount
        
        for t in range(T):
            self.S[t] = self.solver.NumVar(0, self.solver.infinity(), f'S_{t}')
        
        # Objective: minimize total payments (penalties increase balance, not objective)
        objective = self.solver.Objective()
        for j in range(n):
            for t in range(T):
                objective.SetCoefficient(self.X[j, t], 1.0)
                objective.SetCoefficient(self.C[j, t], 1.0)
                objective.SetCoefficient(self.P[j, t], 1.0)
        objective.SetMinimization()
        
        # Constraint 1: Budget constraints
        # Cash each month cannot exceed income plus previous savings (<= form as в статье)
        budget_0 = self.solver.Constraint(-self.solver.infinity(), self.instance.monthly_income[0])
        for j in range(n):
            budget_0.SetCoefficient(self.X[j, 0], 1.0)
            budget_0.SetCoefficient(self.C[j, 0], 1.0)
            budget_0.SetCoefficient(self.P[j, 0], 1.0)
        budget_0.SetCoefficient(self.S[0], 1.0)
        
        # sum_j(X+C+P) + S[t] <= monthly_income[t] + S[t-1] for t >= 1
        for t in range(1, T):
            budget = self.solver.Constraint(-self.solver.infinity(), self.instance.monthly_income[t])
            for j in range(n):
                budget.SetCoefficient(self.X[j, t], 1.0)
                budget.SetCoefficient(self.C[j, t], 1.0)
                budget.SetCoefficient(self.P[j, t], 1.0)
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
            
            # Initial balance at release: B[j, r_j] = principal[j]
            init_balance = self.solver.Constraint(self.instance.principals[j], self.instance.principals[j])
            init_balance.SetCoefficient(self.B[j, r_j], 1.0)
            
            # Balance dynamics: B[j,t] = B[j,t-1]*(1+i[j,t]) - X[j,t] + C[j,t] + P[j,t]
            for t in range(r_j + 1, T):
                i_jt = self.instance.interest_rates[j, t]
                balance_eq = self.solver.Constraint(0, 0)
                balance_eq.SetCoefficient(self.B[j, t], 1.0)
                balance_eq.SetCoefficient(self.B[j, t-1], -(1.0 + i_jt))
                balance_eq.SetCoefficient(self.X[j, t], 1.0)
                balance_eq.SetCoefficient(self.C[j, t], 1.0)
                
                # Cap payment by outstanding balance with interest
                max_payment = self.solver.Constraint(-self.solver.infinity(), 0)
                max_payment.SetCoefficient(self.X[j, t], 1.0)
                max_payment.SetCoefficient(self.B[j, t-1], -(1.0 + i_jt))
        
        # Constraint 3: Loan activity (big-M)
        # B[j,t] <= M * Z[j,t]
        for j in range(n):
            for t in range(self.instance.T):
                activity = self.solver.Constraint(-self.solver.infinity(), 0)
                activity.SetCoefficient(self.B[j, t], 1.0)
                activity.SetCoefficient(self.Z[j, t], -self.M)
                # Payments only when active
                active_pay = self.solver.Constraint(-self.solver.infinity(), 0)
                active_pay.SetCoefficient(self.X[j, t], 1.0)
                active_pay.SetCoefficient(self.Z[j, t], -self.M)
                # Monotonicity of activity: once inactive stays inactive
                if t > 0:
                    monotone = self.solver.Constraint(0, self.solver.infinity())
                    monotone.SetCoefficient(self.Z[j, t-1], 1.0)
                    monotone.SetCoefficient(self.Z[j, t], -1.0)
        
        # Constraint 4: Minimum payment requirement
        # If loan is active (Z[j,t] = 1), payment must be at least min_payment_pct[j] * B[j,t-1]
        # X[j,t] >= min_payment_pct[j] * B[j,t-1] - M*(1 - Z[j,t])
        for j in range(n):
            r_j = self.instance.release_time[j]
            min_pct = self.instance.min_payment_pct[j]
            
            for t in range(r_j + 1, self.instance.T):
                # X - min_pct*B + M*(1 - Z) >= 0
                min_payment = self.solver.Constraint(0, self.solver.infinity())
                min_payment.SetCoefficient(self.X[j, t], 1.0)
                min_payment.SetCoefficient(self.B[j, t-1], -min_pct)
                min_payment.SetCoefficient(self.Z[j, t], self.M)
        
        # Constraint 5: Underpayment penalty
        # C[j,t] >= (min_payment - X[j,t]) * (1 + default_rate) * Z[j,t]
        # Simplified: C[j,t] >= (min_payment_pct * B[j,t-1] - X[j,t]) * (1 + h[j,t]) * Z[j,t]
        for j in range(n):
            r_j = self.instance.release_time[j]
            
            for t in range(r_j + 1, self.instance.T):
                min_pct = self.instance.min_payment_pct[j]
                h_jt = self.instance.default_rates[j, t]
                penalty_mult = 1.0 + h_jt
                
                # C >= penalty_mult * (min_pct * B - X) - M*penalty_mult*(1 - Z)
                underpayment = self.solver.Constraint(-self.M * penalty_mult, self.solver.infinity())
                underpayment.SetCoefficient(self.C[j, t], 1.0)
                underpayment.SetCoefficient(self.B[j, t-1], penalty_mult * min_pct)
                underpayment.SetCoefficient(self.X[j, t], -penalty_mult)
                underpayment.SetCoefficient(self.Z[j, t], self.M * penalty_mult)
        
        # Constraint 6: Overpayment handling
        # Fixed penalty for exceeding stipulated amount, per original формулировке
        for j in range(n):
            prepay_penalty = self.instance.prepay_penalty[j]
            stipulated = self.instance.stipulated_amount[j]
            
            for t in range(self.instance.T):
                # Link overpayment indicator Y
                overpay_cap = self.solver.Constraint(-self.solver.infinity(), stipulated + self.M)
                overpay_cap.SetCoefficient(self.X[j, t], 1.0)
                overpay_cap.SetCoefficient(self.Y[j, t], -self.M)
                
                overpay_floor = self.solver.Constraint(stipulated - self.M, self.solver.infinity())
                overpay_floor.SetCoefficient(self.X[j, t], 1.0)
                overpay_floor.SetCoefficient(self.Y[j, t], -self.M)
                
                # Penalty is fixed when Y=1
                penalty_lb = self.solver.Constraint(0, self.solver.infinity())
                penalty_lb.SetCoefficient(self.P[j, t], 1.0)
                penalty_lb.SetCoefficient(self.Y[j, t], -prepay_penalty)
                
                penalty_ub = self.solver.Constraint(-self.solver.infinity(), 0)
                penalty_ub.SetCoefficient(self.P[j, t], 1.0)
                penalty_ub.SetCoefficient(self.Y[j, t], -prepay_penalty)
                
                # Penalty only if active
                penalty_active = self.solver.Constraint(-self.solver.infinity(), 0)
                penalty_active.SetCoefficient(self.P[j, t], 1.0)
                penalty_active.SetCoefficient(self.Z[j, t], -self.M)
        
        # Constraint 7: Final balance must be zero
        # B[j, T-1] = 0 for all j
        for j in range(n):
            final_balance = self.solver.Constraint(0, 0)
            final_balance.SetCoefficient(self.B[j, T-1], 1.0)
    
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
        
        # Extract solution
        n = self.instance.n
        T = self.instance.T
        
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
        
        # Get objective value
        obj_value = self.solver.Objective().Value()
        
        # Get gap (if available)
        gap = 0.0
        if hasattr(self.solver, 'GetBestObjectiveBound'):
            try:
                best_bound = self.solver.GetBestObjectiveBound()
                if obj_value > 0:
                    gap = abs(best_bound - obj_value) / obj_value * 100
            except:
                pass
        
        # Status mapping
        status_map = {
            pywraplp.Solver.OPTIMAL: "OPTIMAL",
            pywraplp.Solver.FEASIBLE: "FEASIBLE",
            pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
            pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
            pywraplp.Solver.ABNORMAL: "ABNORMAL",
            pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
        }
        status_str = status_map.get(status, f"UNKNOWN_{status}")
        
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


def solve_rpml(instance: RiosSolisInstance, time_limit_seconds: Optional[int] = None) -> RPMLSolution:
    """
    Convenience function to solve RPML instance.
    
    Args:
        instance: Problem instance
        time_limit_seconds: Maximum solve time
    
    Returns:
        RPMLSolution with results
    """
    model = RPMLModel(instance, time_limit_seconds)
    return model.solve()

