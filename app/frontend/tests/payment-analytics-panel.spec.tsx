import { describe, expect, test } from 'bun:test'
import { render, screen } from '@testing-library/react'
import { PaymentAnalyticsPanel } from '../src/components/PaymentAnalytics'

const baseProps = {
  debts: [
    {
      id: 1,
      name: 'Банковский кредит 1',
      principal: 100000,
      fixed_payment: 5000,
      prepay_penalty: 0,
      default_rate_monthly: 0.02,
    },
  ],
  monthlyIncome: [0, 10000],
  horizonMonths: 2,
  baseline: {
    milp_total_cost: 9000,
    avalanche_total_cost: 9500,
    snowball_total_cost: 9800,
  },
  ruModeActive: false,
}

describe('PaymentAnalyticsPanel', () => {
  test('shows exact penalty label when strategy budget trace is available', () => {
    render(
      <PaymentAnalyticsPanel
        {...baseProps}
        strategyResults={{
          milp: {
            total_cost: 9000,
            paymentsMatrix: [[0, 9000]],
            balancesMatrix: [[100000, 93000]],
            savingsVector: [0, 1000],
            budgetTrace: [
              { month: 1, implied_penalty: 0 },
              { month: 2, implied_penalty: 7222.57 },
            ],
          },
        }}
      />,
    )

    expect(screen.getByText(/без накопления в общий график/i)).toBeTruthy()
    expect(screen.getByText(/Штрафы берутся из динамики модели RPML/i)).toBeTruthy()
  })

  test('falls back to estimated penalty label when trace is missing', () => {
    render(
      <PaymentAnalyticsPanel
        {...baseProps}
        strategyResults={{
          milp: {
            total_cost: 9000,
            paymentsMatrix: [[0, 9000]],
            balancesMatrix: [[100000, 93000]],
            savingsVector: [0, 1000],
          },
        }}
      />,
    )

    expect(screen.getByText(/Штрафы показаны как приближенная оценка/i)).toBeTruthy()
  })
})
