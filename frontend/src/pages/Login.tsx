import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Login() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [orgName, setOrgName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const endpoint = mode === 'login' ? '/api/auth/login' : '/api/auth/register'
      const body = mode === 'login'
        ? { email, password }
        : { email, password, display_name: displayName || undefined, org_name: orgName || undefined }

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Authentication failed')
      }

      const data = await res.json()
      localStorage.setItem('veilchat_token', data.access_token)
      localStorage.setItem('veilchat_user', JSON.stringify(data.user))
      navigate('/')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="w-full max-w-md p-8">
        <div className="flex flex-col items-center mb-8">
          <svg width="48" height="56" viewBox="0 0 28 34" fill="none" xmlns="http://www.w3.org/2000/svg" className="mb-4">
            <defs>
              <linearGradient id="lg-s" x1="2" y1="2" x2="26" y2="32" gradientUnits="userSpaceOnUse">
                <stop offset="0" stopColor="#4A5090"/><stop offset="0.5" stopColor="#5B6BC0"/><stop offset="1" stopColor="#7C8BF5"/>
              </linearGradient>
              <linearGradient id="lg-k" x1="10" y1="10" x2="18" y2="26" gradientUnits="userSpaceOnUse">
                <stop offset="0" stopColor="#7C8BF5"/><stop offset="1" stopColor="#9AA5FF"/>
              </linearGradient>
            </defs>
            <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" fill="url(#lg-s)" opacity="0.12"/>
            <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" stroke="url(#lg-s)" strokeWidth="1.8" strokeLinejoin="round" fill="none"/>
            <circle cx="14" cy="14" r="3.5" stroke="url(#lg-k)" strokeWidth="1.5" fill="none"/>
            <line x1="14" y1="17.5" x2="14" y2="24" stroke="url(#lg-k)" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <h1 className="text-2xl font-display font-semibold tracking-[6px]">VEIL<span className="font-light text-veil-500">PROXY</span></h1>
        </div>
        <p className="text-center text-gray-400 mb-8 text-xs font-mono tracking-widest uppercase">
          Enterprise LLM Sanitization Proxy
        </p>

        <div className="flex gap-1 mb-6 bg-gray-800 rounded-lg p-1">
          <button
            onClick={() => setMode('login')}
            className={`flex-1 py-2 rounded text-sm font-medium transition-colors ${
              mode === 'login' ? 'bg-veil-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Sign In
          </button>
          <button
            onClick={() => setMode('register')}
            className={`flex-1 py-2 rounded text-sm font-medium transition-colors ${
              mode === 'register' ? 'bg-veil-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'register' && (
            <>
              <input
                type="text"
                placeholder="Display name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-veil-500"
              />
              <input
                type="text"
                placeholder="Organization name"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-veil-500"
              />
            </>
          )}
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-veil-500"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-veil-500"
          />
          {error && (
            <p className="text-red-400 text-sm">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-veil-600 hover:bg-veil-700 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            {loading ? 'Please wait...' : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </form>
      </div>
    </div>
  )
}
