import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export default function Login() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [orgName, setOrgName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  // Handle OAuth callback token (delivered via URL fragment, never sent to server/logs)
  useEffect(() => {
    const hash = window.location.hash
    const match = hash.match(/oauth_token=([^&]+)/)
    const oauthToken = match ? match[1] : null
    if (oauthToken) {
      // Clear the hash immediately so token isn't visible in URL
      window.history.replaceState(null, '', window.location.pathname)
      localStorage.setItem('veilchat_token', oauthToken)
      fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${oauthToken}` },
      })
        .then(res => {
          if (!res.ok) throw new Error('Failed to fetch user')
          return res.json()
        })
        .then(user => {
          localStorage.setItem('veilchat_user', JSON.stringify(user))
          navigate('/', { replace: true })
        })
        .catch(() => {
          localStorage.removeItem('veilchat_token')
          setError('OAuth login failed. Please try again.')
        })
    }
  }, [navigate])

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

  const handleGoogleLogin = async () => {
    setError('')
    setGoogleLoading(true)
    try {
      const res = await fetch('/api/auth/google/authorize')
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Google login is not available')
      }
      const data = await res.json()
      window.location.href = data.authorize_url
    } catch (err) {
      setError((err as Error).message)
      setGoogleLoading(false)
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

        {/* Google OAuth button */}
        <button
          onClick={handleGoogleLogin}
          disabled={googleLoading}
          className="w-full flex items-center justify-center gap-3 py-3 bg-white hover:bg-gray-100 text-gray-800 rounded-lg font-medium transition-colors disabled:opacity-50 mb-4"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
            <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
            <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
            <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
            <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 6.29C4.672 4.163 6.656 2.58 9 3.58z" fill="#EA4335"/>
          </svg>
          {googleLoading ? 'Redirecting...' : 'Continue with Google'}
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="flex-1 h-px bg-gray-700"></div>
          <span className="text-gray-500 text-xs uppercase tracking-wider">or</span>
          <div className="flex-1 h-px bg-gray-700"></div>
        </div>

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
            minLength={8}
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
          {mode === 'login' && (
            <p className="text-center">
              <Link to="/forgot-password" className="text-veil-400 hover:text-veil-300 text-sm">
                Forgot password?
              </Link>
            </p>
          )}
        </form>
      </div>
    </div>
  )
}
