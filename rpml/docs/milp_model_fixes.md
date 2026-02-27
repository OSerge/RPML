# RPML MILP Model Fixes

## Обзор

Документ описывает исправления в файле `src/rpml/milp_model.py` для устранения проблем с отрицательными savings (cash shortfall) при сравнении MILP-решения с baseline (Debt Avalanche).

**Файл:** `src/rpml/milp_model.py`  
**Дата:** 2026-01-10  
**Статус:** Тестирование показывает положительные savings на выборке инстансов

---

## Найденные баги

### 1. Жёсткое ограничение баланса в месяц выпуска (release month)

**Было (строки 145-147):**
```python
# Initial balance at release: B[j, r_j] = principal[j]
init_balance = self.solver.Constraint(self.instance.principals[j], self.instance.principals[j])
init_balance.SetCoefficient(self.B[j, r_j], 1.0)
```

**Проблема:** Баланс жёстко фиксировался как `B[j,rj] = principal`, но платежи `X[j,rj]` при этом разрешались. Это означало, что платёж в месяц выпуска НЕ уменьшал баланс, что приводило к переплате.

**Исправление:**
```python
# Balance at release month: B[j,r_j] = principal*(1+i) - X[j,r_j] + C[j,r_j]
# Rearranged: B[j,r_j] + X[j,r_j] - C[j,r_j] = principal*(1+i)
i_rj = self.instance.interest_rates[j, r_j]
init_balance_value = self.instance.principals[j] * (1.0 + i_rj)
init_balance = self.solver.Constraint(init_balance_value, init_balance_value)
init_balance.SetCoefficient(self.B[j, r_j], 1.0)
init_balance.SetCoefficient(self.X[j, r_j], 1.0)
init_balance.SetCoefficient(self.C[j, r_j], -1.0)
```

---

### 2. Неправильный знак коэффициента для C в динамике баланса

**Было (строки 149-156):**
```python
balance_eq.SetCoefficient(self.C[j, t], 1.0)  # НЕПРАВИЛЬНО!
```

**Проблема:** Constraint имел вид `B[t] + X[t] + C[t] = B[t-1]*(1+i)`, что давало:
`B[t] = B[t-1]*(1+i) - X[t] - C[t]`

C (штраф за недоплату) **вычитался** из баланса, хотя должен **добавляться** (штраф увеличивает долг).

**Исправление:**
```python
balance_eq.SetCoefficient(self.C[j, t], -1.0)  # C adds to balance (penalty)
```

Теперь: `B[t] + X[t] - C[t] = B[t-1]*(1+i)` → `B[t] = B[t-1]*(1+i) - X[t] + C[t]` ✓

---

### 3. Жёсткое ограничение минимального платежа делало модель INFEASIBLE

**Было:**
```python
# Constraint 4: Minimum payment requirement
# X[j,t] >= min_pct * B_prev - M*(1 - Z[j,t])
min_payment = self.solver.Constraint(-self.M, self.solver.infinity())
min_payment.SetCoefficient(self.X[j, t], 1.0)
min_payment.SetCoefficient(self.B[j, t-1], -min_pct)
min_payment.SetCoefficient(self.Z[j, t], -self.M)
```

**Проблема:** В некоторых инстансах `monthly_income[0] < min_required_payment`. Например:
- Минимальный платёж = 10,715.57
- Доход в первый месяц = 10,290.67

Жёсткое ограничение делало модель **INFEASIBLE**.

**Исправление:** Полностью удалено жёсткое ограничение минимального платежа. Вместо него используется **мягкое ограничение через штраф C** (Constraint 4 - Underpayment penalty):

```python
# Constraint 4: Underpayment penalty (replaces hard minimum payment constraint)
# If Z=1 and X < min_pct*B_prev, then C >= (min_pct*B_prev - X)*(1 + h)
```

Если платёж меньше минимального, штраф C покрывает разницу с учётом default rate.

---

### 4. Двойной учёт штрафа C в objective

**Было:**
```python
objective.SetCoefficient(self.X[j, t], 1.0)
objective.SetCoefficient(self.C[j, t], 1.0)  # ДВОЙНОЙ СЧЁТ!
objective.SetCoefficient(self.P[j, t], 1.0)
```

**Проблема:** C добавлялся в баланс (увеличивая будущие платежи X) И в objective. Это двойной счёт, который завышал стоимость MILP-решения.

**Исправление:**
```python
objective.SetCoefficient(self.X[j, t], 1.0)
# C is NOT in objective - it increases balance which increases future X
objective.SetCoefficient(self.P[j, t], 1.0)  # P is direct fee (currently = 0)
```

---

### 5. Неиспользуемая переменная O и некорректная логика prepayment

**Было:**
```python
self.O[j, t] = self.solver.NumVar(0, self.solver.infinity(), f'O_{j}_{t}')  # overpayment amount
```

**Проблема:** Переменная O создавалась, но не использовалась. Логика prepayment penalty была сложной и некорректной, основанной на `stipulated_amount`, которая в датасете представляет **срок кредита** (3-150), а не сумму платежа.

**Исправление:** Удалена переменная O. Упрощена логика prepayment:
```python
# Constraint 6: Prepayment penalty (simplified)
# Note: stipulated_amount in dataset appears to be loan term, not payment amount
# P[j,t] = 0 for now (no prepayment penalty in simplified model)
for j in range(n):
    for t in range(self.instance.T):
        zero_p = self.solver.Constraint(0, 0)
        zero_p.SetCoefficient(self.P[j, t], 1.0)
```

---

### 6. C и P убраны из бюджетного ограничения

**Было:**
```python
budget_0.SetCoefficient(self.X[j, 0], 1.0)
budget_0.SetCoefficient(self.C[j, 0], 1.0)
budget_0.SetCoefficient(self.P[j, 0], 1.0)
```

**Проблема:** C и P — это штрафы, которые добавляются к долгу/стоимости, но они не расходуют текущий бюджет (income).

**Исправление:**
```python
budget_0.SetCoefficient(self.X[j, 0], 1.0)
# C and P are penalties, not budget expenditures
```

---

## Итоговая структура модели

### Переменные
- `X[j,t]` — платёж по кредиту j в месяц t
- `B[j,t]` — баланс кредита j в конце месяца t
- `Z[j,t]` — бинарный индикатор активности кредита
- `S[t]` — накопления (savings) в конце месяца t
- `C[j,t]` — штраф за недоплату (добавляется к балансу)
- `P[j,t]` — штраф за досрочное погашение (= 0 в упрощённой модели)
- `Y[j,t]` — бинарный индикатор досрочного погашения (не используется)

### Objective
```
minimize sum_{j,t} X[j,t] + P[j,t]
```

### Ограничения

1. **Budget:** `sum_j(X[j,t]) + S[t] <= income[t] + S[t-1]`

2. **Balance dynamics:**
   - Release: `B[j,rj] = principal*(1+i[rj]) - X[j,rj] + C[j,rj]`
   - Other: `B[j,t] = B[j,t-1]*(1+i[t]) - X[j,t] + C[j,t]`

3. **Activity:** `B[j,t] <= M * Z[j,t]`, monotonicity `Z[j,t] <= Z[j,t-1]`

4. **Underpayment penalty:** 
   `C[j,t] >= (min_pct * B_prev - X[j,t]) * (1 + h[j,t])` when `Z[j,t] = 1`

5. **Prepayment:** `P[j,t] = 0` (simplified)

6. **Final balance:** `B[j,T-1] = 0` for all j

---

## Результаты тестирования

### Выборочные тесты (4-loan instances)
| Instance | MILP | Baseline | Savings |
|----------|------|----------|---------|
| Deudas_4_0_0_0_4_120_fijo_fijo_0 | 380,348 | 445,225 | **14.57%** |
| Deudas_4_0_0_0_4_120_fijo_fijo_1 | 658,608 | 664,090 | **0.83%** |
| Deudas_4_0_0_0_4_120_fijo_fijo_2 | 753,428 | 765,753 | **1.61%** |
| Deudas_4_1_1_1_1_120_fijo_fijo_7 | 1,955,246 | 1,979,495 | **1.23%** |

### 8-loan instance
| Instance | MILP | Baseline | Savings |
|----------|------|----------|---------|
| Deudas_8_0_0_0_8_120_fijo_fijo_0 | 1,092,010 | 1,231,740 | **11.34%** |

**Все тестовые savings положительные** — MILP-решение не хуже baseline.

---

## Рекомендации для проверки

1. **Запустить полный эксперимент:**
   ```bash
   cd /home/serge/Dev/RPML
   source .venv/bin/activate
   python run_experiments.py
   ```

2. **Проверить, что все savings >= 0%** (MILP должен быть не хуже baseline)

3. **Сравнить с результатами Rios-Solis:**
   - Ожидаемые средние savings: ~4-6%
   - Максимальные savings: до 25%

4. **Проверить корректность balance dynamics:**
   - Все final balances должны быть 0
   - Платежи не должны превышать текущий долг

---

## Файлы изменений

- `src/rpml/milp_model.py` — основные исправления MILP модели
- `run_experiments.py` — добавлен 12-loan instances в тесты (опционально)
