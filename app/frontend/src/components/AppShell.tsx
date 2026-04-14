import { Link, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { clearStoredToken, useStoredToken } from '@/lib/auth-storage'
import { cn } from '@/lib/utils'

type Props = {
  children: ReactNode
}

export function AppShell({ children }: Props) {
  const navigate = useNavigate()
  const authed = Boolean(useStoredToken())

  function logout() {
    clearStoredToken()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex w-full max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">RPML</h1>
            <p className="text-sm text-muted-foreground">Экспериментальная панель</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <nav className="flex flex-wrap gap-2 text-sm">
              {!authed ? <NavLink to="/login">Вход</NavLink> : null}
              <NavLink to="/debts" disabled={!authed}>
                Долги
              </NavLink>
              <NavLink to="/optimization" disabled={!authed}>
                Оптимизация
              </NavLink>
            </nav>
            {authed ? (
              <button
                type="button"
                onClick={logout}
                className="rounded-md border border-border px-3 py-1.5 text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                Выйти
              </button>
            ) : null}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1600px] px-4 py-6">{children}</main>
    </div>
  )
}

function NavLink({
  to,
  children,
  disabled,
}: {
  to: string
  children: ReactNode
  disabled?: boolean
}) {
  return (
    <Link
      to={to}
      className={cn(
        'rounded-md px-2 py-1 transition-colors',
        disabled
          ? 'pointer-events-none text-muted-foreground/50'
          : 'text-primary hover:bg-accent hover:text-accent-foreground',
      )}
    >
      {children}
    </Link>
  )
}
