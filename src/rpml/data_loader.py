"""
Data loader for Rios-Solis RPML dataset.

Parses .dat files from the dataset published at:
https://doi.org/10.6084/m9.figshare.4823518.v1
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np


PROHIBITED_VALUE = 1e12


@dataclass
class RiosSolisInstance:
    """
    Represents a single RPML problem instance from Rios-Solis dataset.
    
    Attributes:
        name: Instance filename (without extension)
        n: Number of loans
        T: Time horizon (months)
        n_cars: Number of car loans
        n_houses: Number of house loans (mortgages)
        n_credit_cards: Number of credit card debts
        n_bank_loans: Number of bank loans
        principals: Initial loan amounts, shape (n,)
        interest_rates: Monthly interest rates, shape (n, T)
        default_rates: Penalty rates when missing min payment, shape (n, T)
        min_payment_pct: Percentage of balance for minimum payment, shape (n,)
        prepay_penalty: Penalty for prepayment (1e12 = prohibited), shape (n,)
        monthly_income: Available budget each month, shape (T,)
        release_time: Month when each loan was issued (0-indexed), shape (n,)
        stipulated_amount: Contractual monthly payment, shape (n,)
        fixed_payment: Fixed payment amount (if applicable), shape (n,)
    """
    name: str
    n: int
    T: int
    n_cars: int
    n_houses: int
    n_credit_cards: int
    n_bank_loans: int
    principals: np.ndarray
    interest_rates: np.ndarray
    default_rates: np.ndarray
    min_payment_pct: np.ndarray
    prepay_penalty: np.ndarray
    monthly_income: np.ndarray
    release_time: np.ndarray
    stipulated_amount: np.ndarray
    fixed_payment: np.ndarray
    
    def __post_init__(self):
        """Validate array shapes after initialization."""
        assert self.principals.shape == (self.n,), f"principals shape mismatch: {self.principals.shape}"
        assert self.interest_rates.shape == (self.n, self.T), f"interest_rates shape mismatch: {self.interest_rates.shape}"
        assert self.default_rates.shape == (self.n, self.T), f"default_rates shape mismatch: {self.default_rates.shape}"
        assert self.min_payment_pct.shape == (self.n,), f"min_payment_pct shape mismatch"
        assert self.prepay_penalty.shape == (self.n,), f"prepay_penalty shape mismatch"
        assert self.monthly_income.shape == (self.T,), f"monthly_income shape mismatch: {self.monthly_income.shape}"
        assert self.release_time.shape == (self.n,), f"release_time shape mismatch"
        assert self.stipulated_amount.shape == (self.n,), f"stipulated_amount shape mismatch"
        assert self.fixed_payment.shape == (self.n,), f"fixed_payment shape mismatch"
    
    @property
    def total_debt(self) -> float:
        """Total initial debt amount."""
        return float(np.sum(self.principals))
    
    @property
    def avg_interest_rate(self) -> float:
        """Average interest rate across all loans and periods."""
        return float(np.mean(self.interest_rates))
    
    def is_prepayment_allowed(self, loan_idx: int) -> bool:
        """Check if prepayment is allowed for a specific loan."""
        return bool(self.prepay_penalty[loan_idx] < PROHIBITED_VALUE * 0.1)


def _parse_vector(line: str) -> np.ndarray:
    """Parse a space-separated line into numpy array."""
    return np.array([float(x) for x in line.strip().split()])


def _parse_int_vector(line: str) -> np.ndarray:
    """Parse a space-separated line into numpy int array."""
    return np.array([int(float(x)) for x in line.strip().split()])


def load_instance(path: Path | str) -> RiosSolisInstance:
    """
    Load a single RPML instance from a .dat file.
    
    File format (from HowToReadTheInstances.txt):
    - Line 1: n T (number of loans, time horizon)
    - Line 2: n_cars n_houses n_credit_cards n_bank_loans
    - Line 3: principals (n values)
    - Lines 4..(3+n): interest_rates matrix (n rows, T columns each)
    - Lines (4+n)..(3+2n): default_rates matrix (n rows, T columns each)
    - Line (4+2n): min_payment_pct (n values)
    - Line (5+2n): prepay_penalty (n values)
    - Line (6+2n): monthly_income (T values)
    - Line (7+2n): release_time (n values)
    - Line (8+2n): stipulated_amount (n values)
    - Line (9+2n): fixed_payment (n values)
    
    Note: 1000000000000.0 indicates prohibited entries.
    """
    path = Path(path)
    
    with open(path, 'r') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    
    # Line 1: n T
    parts = lines[0].split()
    n = int(parts[0])
    T = int(parts[1])
    
    # Line 2: loan type counts
    type_counts = _parse_int_vector(lines[1])
    n_cars = int(type_counts[0])
    n_houses = int(type_counts[1])
    n_credit_cards = int(type_counts[2])
    n_bank_loans = int(type_counts[3])
    
    # Line 3: principals
    principals = _parse_vector(lines[2])
    
    # Lines 4..(3+n): interest_rates matrix
    interest_rates = np.zeros((n, T))
    for i in range(n):
        interest_rates[i, :] = _parse_vector(lines[3 + i])
    
    # Lines (4+n)..(3+2n): default_rates matrix
    default_rates = np.zeros((n, T))
    for i in range(n):
        default_rates[i, :] = _parse_vector(lines[3 + n + i])
    
    # Line (4+2n): min_payment_pct
    min_payment_pct = _parse_vector(lines[3 + 2*n])
    
    # Line (5+2n): prepay_penalty
    prepay_penalty = _parse_vector(lines[4 + 2*n])
    
    # Line (6+2n): monthly_income
    monthly_income = _parse_vector(lines[5 + 2*n])
    
    # Line (7+2n): release_time
    release_time = _parse_int_vector(lines[6 + 2*n])
    
    # Line (8+2n): stipulated_amount
    stipulated_amount = _parse_vector(lines[7 + 2*n])
    
    # Line (9+2n): fixed_payment (may not exist in all files)
    if len(lines) > 8 + 2*n:
        fixed_payment = _parse_vector(lines[8 + 2*n])
    else:
        fixed_payment = np.zeros(n)
    
    return RiosSolisInstance(
        name=path.stem,
        n=n,
        T=T,
        n_cars=n_cars,
        n_houses=n_houses,
        n_credit_cards=n_credit_cards,
        n_bank_loans=n_bank_loans,
        principals=principals,
        interest_rates=interest_rates,
        default_rates=default_rates,
        min_payment_pct=min_payment_pct,
        prepay_penalty=prepay_penalty,
        monthly_income=monthly_income,
        release_time=release_time,
        stipulated_amount=stipulated_amount,
        fixed_payment=fixed_payment,
    )


def load_all_instances(directory: Path | str) -> List[RiosSolisInstance]:
    """
    Load all .dat instances from a directory.
    
    Returns instances sorted by (n, name) for reproducibility.
    """
    directory = Path(directory)
    instances = []
    
    for dat_file in sorted(directory.glob("**/*.dat")):
        try:
            instance = load_instance(dat_file)
            instances.append(instance)
        except Exception as e:
            print(f"Warning: Failed to load {dat_file}: {e}")
    
    # Sort by number of loans, then by name
    instances.sort(key=lambda x: (x.n, x.name))
    return instances


def get_instances_by_size(instances: List[RiosSolisInstance]) -> dict:
    """
    Group instances by number of loans.
    
    Returns dict with keys 4, 8, 12 mapping to lists of instances.
    """
    grouped = {4: [], 8: [], 12: []}
    for inst in instances:
        if inst.n in grouped:
            grouped[inst.n].append(inst)
    return grouped
