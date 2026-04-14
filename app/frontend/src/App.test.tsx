/// <reference lib="dom" />
import { test } from 'bun:test'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from './App'

test('renders app shell', () => {
  render(
    <MemoryRouter>
      <AppRoutes />
    </MemoryRouter>,
  )
  screen.getByText(/RPML/i)
})
