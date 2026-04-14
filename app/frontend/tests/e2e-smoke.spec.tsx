/// <reference lib="dom" />
import { beforeEach, describe, expect, test } from 'bun:test'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../src/App'
import { clearStoredToken } from '../src/lib/auth-storage'

describe('e2e-smoke (routing / login shell)', () => {
  beforeEach(() => {
    localStorage.clear()
    clearStoredToken()
  })

  test('root redirects to login shell', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: /вход/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /войти/i })).toBeTruthy()
  })

  test('/login shows login shell and RPML header', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <AppRoutes />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: /^rpml$/i })).toBeTruthy()
    expect(screen.getByRole('link', { name: /вход/i })).toBeTruthy()
    expect(screen.getByRole('heading', { name: /вход/i })).toBeTruthy()
  })

  test('/debts without token redirects to login (protected route)', () => {
    render(
      <MemoryRouter initialEntries={['/debts']}>
        <AppRoutes />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: /вход/i })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: /долги/i })).toBeNull()
  })
})
