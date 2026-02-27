import { useState } from 'react'
import { Send, Sparkles, TrendingUp, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { motion } from 'motion/react'
import { explainQuestion } from '../services/api'

interface Message {
  id: string
  type: 'user' | 'agent'
  content: string
  timestamp: Date
  insights?: {
    type: 'warning' | 'success' | 'info'
    title: string
    description: string
  }[]
}

export function Agent() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      type: 'agent',
      content: 'Здравствуйте! Я проанализировал ваши финансы. У меня есть несколько важных рекомендаций.',
      timestamp: new Date(),
      insights: [
        {
          type: 'warning',
          title: 'Высокая ставка по кредитке',
          description: 'Кредитная карта имеет высокую ставку. Рекомендую погасить её в первую очередь.',
        },
        {
          type: 'success',
          title: 'Возможность досрочного погашения',
          description: 'При текущих доходах вы можете погасить кредитку досрочно и сэкономить на процентах.',
        },
        {
          type: 'info',
          title: 'Оптимизация платежей',
          description: 'Я могу создать оптимальный план погашения для экономии средств.',
        },
      ],
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSend = async () => {
    if (!input.trim() || loading) return

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: input,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const response = await explainQuestion(input, '')
      
      const agentMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'agent',
        content: response || 'Получен ответ от сервера',
        timestamp: new Date(),
      }

      setMessages((prev) => [...prev, agentMessage])
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'agent',
        content: `Ошибка при получении ответа: ${(error as Error).message}`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, errorMessage])
    } finally {
      setLoading(false)
    }
  }

  const quickActions = [
    'Как быстрее погасить кредитку?',
    'Покажи сценарий досрочного погашения',
    'Какие долги приоритетные?',
    'Сколько я переплачу по процентам?',
  ]

  return (
    <div className="h-[calc(100vh-180px)] flex flex-col bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-950/30 dark:to-purple-950/30">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <div>
            <h2 className="text-slate-900 dark:text-white font-semibold">AI Финансовый Агент</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">Персональные рекомендации на основе ваших данных</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map((message) => (
          <motion.div
            key={message.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`max-w-[85%] md:max-w-[70%] ${message.type === 'user' ? 'order-2' : 'order-1'}`}>
              <div
                className={`rounded-2xl px-4 py-3 ${
                  message.type === 'user'
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-100 dark:bg-slate-700 text-slate-900 dark:text-white'
                }`}
              >
                {message.content}
              </div>

              {/* Insights */}
              {message.insights && (
                <div className="mt-3 space-y-2">
                  {message.insights.map((insight, idx) => (
                    <div
                      key={idx}
                      className={`rounded-xl p-4 border ${
                        insight.type === 'warning'
                          ? 'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800'
                          : insight.type === 'success'
                          ? 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800'
                          : 'bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5">
                          {insight.type === 'warning' && (
                            <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                          )}
                          {insight.type === 'success' && (
                            <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
                          )}
                          {insight.type === 'info' && (
                            <TrendingUp className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div
                            className={`text-sm mb-1 font-medium ${
                              insight.type === 'warning'
                                ? 'text-amber-900 dark:text-amber-100'
                                : insight.type === 'success'
                                ? 'text-green-900 dark:text-green-100'
                                : 'text-blue-900 dark:text-blue-100'
                            }`}
                          >
                            {insight.title}
                          </div>
                          <p
                            className={`text-sm ${
                              insight.type === 'warning'
                                ? 'text-amber-700 dark:text-amber-300'
                                : insight.type === 'success'
                                ? 'text-green-700 dark:text-green-300'
                                : 'text-blue-700 dark:text-blue-300'
                            }`}
                          >
                            {insight.description}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="text-xs text-slate-400 dark:text-slate-500 mt-1 px-1">
                {message.timestamp.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </motion.div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-100 dark:bg-slate-700 rounded-2xl px-4 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Quick Actions */}
      {messages.length === 1 && (
        <div className="px-6 py-3 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-2">Быстрые вопросы:</p>
          <div className="flex flex-wrap gap-2">
            {quickActions.map((action, idx) => (
              <button
                key={idx}
                onClick={() => setInput(action)}
                className="px-3 py-1.5 text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-full hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors text-slate-700 dark:text-slate-300"
              >
                {action}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Задайте вопрос о ваших финансах..."
            className="flex-1 px-4 py-3 bg-slate-100 dark:bg-slate-700 border-0 rounded-xl text-slate-900 dark:text-white placeholder:text-slate-500 dark:placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            disabled={loading}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="w-12 h-12 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 dark:disabled:bg-slate-700 flex items-center justify-center transition-colors"
          >
            <Send className="w-5 h-5 text-white" />
          </button>
        </div>
      </div>
    </div>
  )
}
