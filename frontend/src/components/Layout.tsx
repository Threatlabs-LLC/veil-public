import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import Sidebar from './Sidebar'
import { rateLimitState } from '../api/client'

export default function Layout() {
  const [rateLimited, setRateLimited] = useState(false)
  const [countdown, setCountdown] = useState(0)

  useEffect(() => {
    return rateLimitState.subscribe((limited, retryAfter) => {
      setRateLimited(limited)
      setCountdown(retryAfter)
    })
  }, [])

  useEffect(() => {
    if (countdown <= 0) return
    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timer)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [rateLimited])

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        {rateLimited && (
          <div className="flex items-center gap-2 px-4 py-2 bg-yellow-900/40 border-b border-yellow-700/50 text-yellow-300 text-sm">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Rate limit reached. Retrying in {countdown}s...</span>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}
