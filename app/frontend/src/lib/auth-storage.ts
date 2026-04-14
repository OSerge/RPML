import { useSyncExternalStore } from 'react'

const KEY = 'rpml_access_token'
const AUTH_CHANGE_EVENT = 'rpml:auth-token-change'

function emitAuthTokenChange(): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT))
}

export function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(KEY)
}

export function setStoredToken(token: string): void {
  if (typeof window === 'undefined') return
  if (window.localStorage.getItem(KEY) === token) return
  window.localStorage.setItem(KEY, token)
  emitAuthTokenChange()
}

export function clearStoredToken(): void {
  if (typeof window === 'undefined') return
  if (window.localStorage.getItem(KEY) === null) return
  window.localStorage.removeItem(KEY)
  emitAuthTokenChange()
}

function subscribeStoredToken(listener: () => void): () => void {
  if (typeof window === 'undefined') {
    return () => {}
  }

  const handleStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === KEY) {
      listener()
    }
  }
  const handleAuthChange = () => {
    listener()
  }

  window.addEventListener('storage', handleStorage)
  window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange)

  return () => {
    window.removeEventListener('storage', handleStorage)
    window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange)
  }
}

export function useStoredToken(): string | null {
  return useSyncExternalStore(subscribeStoredToken, getStoredToken, () => null)
}
