import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { LogOut } from 'lucide-react'
import { Plan } from './components/Plan'
import { Agent } from './components/Agent'
import { Login } from './pages/Login'
import { ProtectedRoute } from './components/ProtectedRoute'
import { getSupabase } from './lib/supabase'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function MainApp() {
  const [activeTab, setActiveTab] = useState<'agent' | 'plan'>('plan')
  const navigate = useNavigate()

  const handleLogout = async () => {
    const client = getSupabase()
    if (client) {
      await client.auth.signOut()
      navigate('/login')
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900">
      <header className="border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
                <svg
                  className="w-6 h-6 text-white"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M6 4 L6 20 L9 20 L9 11 L15 20 L18 20 L18 4 L15 4 L15 13 L9 4 Z" />
                </svg>
              </div>
              <div>
                <h1 className="text-slate-900 dark:text-white font-semibold">
                  NUMEX
                </h1>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  Твои долги под контролем
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className="relative bg-slate-100 dark:bg-slate-800 p-1 rounded-full flex gap-1">
                <motion.div
                  className="absolute top-1 bottom-1 bg-white dark:bg-slate-700 rounded-full shadow-md"
                  initial={false}
                  animate={{
                    left: activeTab === 'plan' ? '4px' : '50%',
                    right: activeTab === 'plan' ? '50%' : '4px',
                  }}
                  transition={{
                    type: 'spring',
                    stiffness: 300,
                    damping: 30,
                  }}
                />
                <button
                  onClick={() => setActiveTab('plan')}
                  className={`relative z-10 px-6 py-2 rounded-full transition-colors ${
                    activeTab === 'plan'
                      ? 'text-slate-900 dark:text-white'
                      : 'text-slate-500 dark:text-slate-400'
                  }`}
                >
                  План
                </button>
                <button
                  onClick={() => setActiveTab('agent')}
                  className={`relative z-10 px-6 py-2 rounded-full transition-colors ${
                    activeTab === 'agent'
                      ? 'text-slate-900 dark:text-white'
                      : 'text-slate-500 dark:text-slate-400'
                  }`}
                >
                  Агент
                </button>
              </div>

              <button
                onClick={handleLogout}
                className="p-2 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
                title="Выйти"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.3 }}
        >
          {activeTab === 'plan' ? <Plan /> : <Agent />}
        </motion.div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MainApp />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
