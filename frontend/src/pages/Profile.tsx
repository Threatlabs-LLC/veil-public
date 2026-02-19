import { useEffect, useState } from 'react'
import { User, Save, Lock, Mail, ShieldCheck } from 'lucide-react'

interface UserProfile {
  id: string
  email: string
  display_name: string | null
  role: string
  organization_id: string
}

export default function Profile() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  // Password change
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [pwSaving, setPwSaving] = useState(false)
  const [pwMessage, setPwMessage] = useState('')
  const [pwError, setPwError] = useState('')

  const token = localStorage.getItem('veilchat_token')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }

  useEffect(() => {
    fetch('/api/auth/me', { headers })
      .then(r => r.json())
      .then((data) => {
        setProfile(data)
        setDisplayName(data.display_name || '')
        setEmail(data.email)
      })
      .catch(e => setError(e.message))
  }, [])

  const handleSaveProfile = async () => {
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const res = await fetch('/api/auth/profile', {
        method: 'PATCH', headers,
        body: JSON.stringify({ display_name: displayName, email }),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Failed to save')
      }
      const updated = await res.json()
      setProfile(updated)
      // Update localStorage user
      const stored = localStorage.getItem('veilchat_user')
      if (stored) {
        const user = JSON.parse(stored)
        user.display_name = updated.display_name
        user.email = updated.email
        localStorage.setItem('veilchat_user', JSON.stringify(user))
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleChangePassword = async () => {
    setPwError('')
    setPwMessage('')
    if (newPassword !== confirmPassword) {
      setPwError('Passwords do not match')
      return
    }
    if (newPassword.length < 8) {
      setPwError('Password must be at least 8 characters')
      return
    }
    setPwSaving(true)
    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST', headers,
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Failed to change password')
      }
      setPwMessage('Password changed successfully')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setTimeout(() => setPwMessage(''), 5000)
    } catch (e) {
      setPwError((e as Error).message)
    } finally {
      setPwSaving(false)
    }
  }

  if (!profile) return <div className="p-6 text-gray-500">Loading...</div>

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="h-14 border-b border-gray-800 flex items-center px-4 gap-4">
        <User className="w-5 h-5 text-veil-500" />
        <span className="font-medium">Profile</span>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl space-y-8">
          {/* Profile Info */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <User className="w-4 h-4 text-gray-400" />
              <h2 className="text-lg font-semibold">Account Information</h2>
            </div>

            <div className="flex items-center gap-4 mb-6 p-4 bg-gray-800/50 border border-gray-700 rounded-xl">
              <div className="w-16 h-16 rounded-full bg-veil-600 flex items-center justify-center text-2xl font-bold">
                {(profile.display_name ?? profile.email).charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="font-medium text-lg">{profile.display_name || profile.email}</div>
                <div className="text-sm text-gray-400">{profile.email}</div>
                <div className="flex items-center gap-1.5 mt-1">
                  <ShieldCheck className="w-3 h-3 text-veil-400" />
                  <span className="text-xs text-veil-400 capitalize">{profile.role}</span>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Display Name</label>
                <input
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-veil-500"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    className="w-full pl-10 pr-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-veil-500"
                  />
                </div>
              </div>
            </div>

            {error && <p className="text-red-400 text-sm mt-2">{error}</p>}

            <button
              onClick={handleSaveProfile}
              disabled={saving || (displayName === (profile.display_name || '') && email === profile.email)}
              className="mt-4 flex items-center gap-2 px-6 py-2.5 bg-veil-600 hover:bg-veil-700 rounded-lg font-medium transition-colors disabled:opacity-40"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Profile'}
            </button>
          </section>

          {/* Password Change */}
          <section className="border-t border-gray-800 pt-8">
            <div className="flex items-center gap-2 mb-4">
              <Lock className="w-4 h-4 text-gray-400" />
              <h2 className="text-lg font-semibold">Change Password</h2>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Current Password</label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-veil-500"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">New Password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-veil-500"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Confirm New Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-veil-500"
                />
              </div>
            </div>

            {pwError && <p className="text-red-400 text-sm mt-2">{pwError}</p>}
            {pwMessage && <p className="text-green-400 text-sm mt-2">{pwMessage}</p>}

            <button
              onClick={handleChangePassword}
              disabled={pwSaving || !currentPassword || !newPassword}
              className="mt-4 flex items-center gap-2 px-6 py-2.5 bg-gray-700 hover:bg-gray-600 rounded-lg font-medium transition-colors disabled:opacity-40"
            >
              <Lock className="w-4 h-4" />
              {pwSaving ? 'Changing...' : 'Change Password'}
            </button>
          </section>
        </div>
      </div>
    </div>
  )
}
