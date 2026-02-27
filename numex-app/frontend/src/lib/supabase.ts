import { createClient, SupabaseClient } from '@supabase/supabase-js'

const url = (import.meta.env.VITE_SUPABASE_URL as string) ?? ''
const anonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY as string) ?? ''

let _client: SupabaseClient | null = null

export function getSupabase(): SupabaseClient | null {
  if (!url || !anonKey) return null
  if (!_client) _client = createClient(url, anonKey)
  return _client
}

export const supabase = getSupabase()

export function isSupabaseConfigured(): boolean {
  return Boolean(url && anonKey)
}
