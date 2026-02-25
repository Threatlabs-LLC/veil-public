import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [available, setAvailable] = useState(true)

  useEffect(() => {
    fetch('/api/auth/capabilities')
      .then(res => res.json())
      .then(data => { if (!data.password_reset) setAvailable(false) })
      .catch(() => {})
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.forgotPassword(email)
      setSent(true)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="w-full max-w-md p-8">
        <h1 className="text-2xl font-display font-semibold text-center mb-2">Reset Password</h1>
        <p className="text-center text-gray-400 mb-8 text-sm">
          Enter your email and we'll send you a reset link.
        </p>

        {!available ? (
          <div className="text-center">
            <div className="bg-yellow-900/30 border border-yellow-700 rounded-lg p-4 mb-6">
              <p className="text-yellow-300 text-sm">
                Password reset is unavailable. Contact your administrator.
              </p>
            </div>
            <Link to="/login" className="text-veil-400 hover:text-veil-300 text-sm">
              Back to Sign In
            </Link>
          </div>
        ) : sent ? (
          <div className="text-center">
            <div className="bg-green-900/30 border border-green-700 rounded-lg p-4 mb-6">
              <p className="text-green-300 text-sm">
                If that email is registered, a reset link has been sent. Check your inbox.
              </p>
            </div>
            <Link to="/login" className="text-veil-400 hover:text-veil-300 text-sm">
              Back to Sign In
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-veil-500"
            />
            {error && <p className="text-red-400 text-sm">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-veil-600 hover:bg-veil-700 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              {loading ? 'Sending...' : 'Send Reset Link'}
            </button>
            <p className="text-center">
              <Link to="/login" className="text-veil-400 hover:text-veil-300 text-sm">
                Back to Sign In
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  )
}
