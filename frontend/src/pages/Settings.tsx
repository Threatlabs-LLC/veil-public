import { useEffect, useState } from 'react'
import { Save, Key, Cpu, SlidersHorizontal, Plus, Trash2, Copy, Check, AlertTriangle, Building, Award, Upload, X, ShieldCheck } from 'lucide-react'
import { api } from '../api/client'
import type { ApiKeyData } from '../api/client'

interface OrgSettings {
  openai_api_key: string
  anthropic_api_key: string
  ollama_base_url: string
  default_provider: string
  default_model: string
  sanitization_enabled: boolean
  min_confidence: number
}

export default function Settings() {
  const [settings, setSettings] = useState<OrgSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  // Track what the user has changed (so we don't overwrite masked keys)
  const [changes, setChanges] = useState<Partial<OrgSettings>>({})

  useEffect(() => {
    const token = localStorage.getItem('veilchat_token')
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
    fetch('/api/settings', { headers })
      .then((r) => r.json())
      .then(setSettings)
      .catch((e) => setError(e.message))
  }, [])

  const handleChange = (key: keyof OrgSettings, value: string | boolean | number) => {
    setChanges((prev) => ({ ...prev, [key]: value }))
    setSettings((prev) => prev ? { ...prev, [key]: value } : prev)
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      const token = localStorage.getItem('veilchat_token')
      const res = await fetch('/api/settings', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(changes),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Failed to save')
      }
      const updated = await res.json()
      setSettings(updated)
      setChanges({})
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (!settings) return <div className="p-6 text-gray-500">Loading...</div>

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="h-14 border-b border-gray-800 flex items-center px-4 gap-4">
        <SlidersHorizontal className="w-5 h-5 text-veil-500" />
        <span className="font-medium">Settings</span>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl space-y-8">
          {/* API Keys */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <Key className="w-4 h-4 text-gray-400" />
              <h2 className="text-lg font-semibold">Provider API Keys</h2>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">OpenAI API Key</label>
                <input
                  type="password"
                  value={changes.openai_api_key ?? settings.openai_api_key}
                  onChange={(e) => handleChange('openai_api_key', e.target.value)}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-veil-500 font-mono text-sm"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Anthropic API Key</label>
                <input
                  type="password"
                  value={changes.anthropic_api_key ?? settings.anthropic_api_key}
                  onChange={(e) => handleChange('anthropic_api_key', e.target.value)}
                  placeholder="sk-ant-..."
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-veil-500 font-mono text-sm"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Ollama Base URL</label>
                <input
                  type="text"
                  value={changes.ollama_base_url ?? settings.ollama_base_url}
                  onChange={(e) => handleChange('ollama_base_url', e.target.value)}
                  placeholder="http://localhost:11434/v1"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-600 focus:outline-none focus:border-veil-500 font-mono text-sm"
                />
                <p className="text-xs text-gray-500 mt-1">Local Ollama instance — no API key required</p>
              </div>
            </div>
          </section>

          {/* Model Defaults */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <Cpu className="w-4 h-4 text-gray-400" />
              <h2 className="text-lg font-semibold">Model Defaults</h2>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Default Provider</label>
                <select
                  value={changes.default_provider ?? settings.default_provider}
                  onChange={(e) => handleChange('default_provider', e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-veil-500"
                >
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="ollama">Ollama (Local)</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Default Model</label>
                <input
                  type="text"
                  value={changes.default_model ?? settings.default_model}
                  onChange={(e) => handleChange('default_model', e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-veil-500 text-sm"
                />
              </div>
            </div>
          </section>

          {/* Sanitization */}
          <section>
            <div className="flex items-center gap-2 mb-4">
              <ShieldCheck className="w-4 h-4 text-gray-400" />
              <h2 className="text-lg font-semibold">Sanitization</h2>
            </div>
            <div className="space-y-4">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={changes.sanitization_enabled ?? settings.sanitization_enabled}
                  onChange={(e) => handleChange('sanitization_enabled', e.target.checked)}
                  className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-veil-600 focus:ring-veil-500"
                />
                <span className="text-sm">Enable automatic PII sanitization</span>
              </label>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Minimum Confidence Threshold: {((changes.min_confidence ?? settings.min_confidence) * 100).toFixed(0)}%
                </label>
                <input
                  type="range"
                  min="0.1"
                  max="1"
                  step="0.05"
                  value={changes.min_confidence ?? settings.min_confidence}
                  onChange={(e) => handleChange('min_confidence', parseFloat(e.target.value))}
                  className="w-full accent-veil-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>Aggressive (10%)</span>
                  <span>Conservative (100%)</span>
                </div>
              </div>
            </div>
          </section>

          {/* Save */}
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            onClick={handleSave}
            disabled={saving || Object.keys(changes).length === 0}
            className="flex items-center gap-2 px-6 py-2.5 bg-veil-600 hover:bg-veil-700 rounded-lg font-medium transition-colors disabled:opacity-40"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Changes'}
          </button>

          {/* Organization */}
          <OrgSection />

          {/* License */}
          <LicenseSection />

          {/* VeilProxy API Keys */}
          <ApiKeysSection />
        </div>
      </div>
    </div>
  )
}

interface OrgProfile {
  name: string
  slug: string
  tier: string
  max_users: number
  is_active: boolean
  user_count: number
}

function OrgSection() {
  const [org, setOrg] = useState<OrgProfile | null>(null)
  const [name, setName] = useState('')
  const [orgSaving, setOrgSaving] = useState(false)
  const [orgSaved, setOrgSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('veilchat_token')
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
    fetch('/api/settings/org', { headers })
      .then(r => r.json())
      .then((data: OrgProfile) => {
        setOrg(data)
        setName(data.name)
      })
      .catch((e) => setError(e.message))
  }, [])

  const handleSaveOrg = async () => {
    setOrgSaving(true)
    try {
      const token = localStorage.getItem('veilchat_token')
      const res = await fetch('/api/settings/org', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ name }),
      })
      if (res.ok) {
        const updated = await res.json()
        setOrg(updated)
        setOrgSaved(true)
        setTimeout(() => setOrgSaved(false), 3000)
      }
    } catch (e) { setError((e as Error).message) } finally {
      setOrgSaving(false)
    }
  }

  if (!org) return null

  const tierColors: Record<string, string> = {
    free: 'bg-gray-700 text-gray-300',
    pro: 'bg-veil-900/50 text-veil-300',
    enterprise: 'bg-amber-900/50 text-amber-300',
  }

  return (
    <section className="border-t border-gray-800 pt-8">
      <div className="flex items-center gap-2 mb-4">
        <Building className="w-4 h-4 text-gray-400" />
        <h2 className="text-lg font-semibold">Organization</h2>
      </div>

      <div className="flex items-center gap-4 mb-4 p-4 bg-gray-800/50 border border-gray-700 rounded-xl">
        <div className="w-12 h-12 rounded-xl bg-veil-600/30 flex items-center justify-center text-xl font-bold text-veil-400">
          {org.name.charAt(0).toUpperCase()}
        </div>
        <div className="flex-1">
          <div className="font-medium">{org.name}</div>
          <div className="text-xs text-gray-400 mt-0.5">
            <span className="font-mono">{org.slug}</span>
            <span className="mx-2 opacity-30">|</span>
            {org.user_count} / {org.max_users} users
          </div>
        </div>
        <span className={`px-2.5 py-1 rounded text-xs font-medium uppercase ${tierColors[org.tier] || 'bg-gray-700'}`}>
          {org.tier}
        </span>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Organization Name</label>
          <input
            value={name}
            onChange={e => { setName(e.target.value); setOrgSaved(false) }}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-veil-500"
          />
        </div>
      </div>
      {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
      <button
        onClick={handleSaveOrg}
        disabled={orgSaving || name === org.name}
        className="mt-4 flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
      >
        <Save className="w-3.5 h-3.5" />
        {orgSaving ? 'Saving...' : orgSaved ? 'Saved!' : 'Update Organization'}
      </button>
    </section>
  )
}

interface LicenseStatus {
  tier: string
  tier_name: string
  max_users: number
  features: string[]
  is_licensed: boolean
  expires_at: string | null
  days_remaining: number | null
  license_id: string | null
}

function LicenseSection() {
  const [license, setLicense] = useState<LicenseStatus | null>(null)
  const [showUpload, setShowUpload] = useState(false)
  const [licenseKey, setLicenseKey] = useState('')
  const [activating, setActivating] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const load = () =>
    api.getLicenseStatus().then(setLicense).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const handleActivate = async () => {
    setActivating(true)
    setError('')
    setSuccess('')
    try {
      await api.activateLicense(licenseKey.trim())
      setSuccess('License activated successfully!')
      setLicenseKey('')
      setShowUpload(false)
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setActivating(false)
    }
  }

  const handleDeactivate = async () => {
    if (!window.confirm('Revert to Community plan? Paid features will be disabled.')) return
    try {
      await api.deactivateLicense()
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!license) return null

  const tierColors: Record<string, string> = {
    free: 'bg-gray-700 text-gray-300',
    team: 'bg-veil-900/50 text-veil-300',
    business: 'bg-blue-900/50 text-blue-300',
    enterprise: 'bg-amber-900/50 text-amber-300',
  }

  return (
    <section className="border-t border-gray-800 pt-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Award className="w-4 h-4 text-gray-400" />
          <h2 className="text-lg font-semibold">License & Plan</h2>
        </div>
        {!showUpload && (
          <button
            onClick={() => { setShowUpload(true); setError(''); setSuccess('') }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors"
          >
            <Upload className="w-4 h-4" /> Activate License
          </button>
        )}
      </div>

      {/* Current plan */}
      <div className="p-4 bg-gray-800/50 border border-gray-700 rounded-xl mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <span className={`px-2.5 py-1 rounded text-xs font-medium uppercase ${tierColors[license.tier] || 'bg-gray-700'}`}>
              {license.tier_name}
            </span>
            {license.is_licensed && license.days_remaining !== null && (
              <span className={`text-xs ${license.days_remaining < 30 ? 'text-amber-400' : 'text-gray-400'}`}>
                {license.days_remaining} days remaining
              </span>
            )}
          </div>
          {license.is_licensed && (
            <button
              onClick={handleDeactivate}
              className="text-xs text-red-400 hover:text-red-300 transition-colors"
            >
              Deactivate
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Max Users</span>
            <p className="font-medium">{license.max_users >= 999999 ? 'Unlimited' : license.max_users}</p>
          </div>
          <div>
            <span className="text-gray-500">Features</span>
            <p className="font-medium">{license.features.length > 0 ? license.features.length : 'Core only'}</p>
          </div>
        </div>

        {license.features.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {license.features.map((f) => (
              <span key={f} className="px-2 py-0.5 bg-gray-700/50 rounded text-xs text-gray-300">
                {f.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        )}
      </div>

      {success && <p className="text-green-400 text-sm mb-3">{success}</p>}
      {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

      {/* Upload form */}
      {showUpload && (
        <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 mb-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium">Paste License Key</label>
            <button onClick={() => setShowUpload(false)} className="p-1 rounded hover:bg-gray-700">
              <X className="w-4 h-4 text-gray-400" />
            </button>
          </div>
          <textarea
            value={licenseKey}
            onChange={(e) => setLicenseKey(e.target.value)}
            placeholder="eyJhbGciOiJSUzI1NiIs..."
            rows={3}
            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white font-mono text-xs placeholder-gray-600 focus:outline-none focus:border-veil-500 resize-none"
          />
          <button
            onClick={handleActivate}
            disabled={activating || !licenseKey.trim()}
            className="mt-2 flex items-center gap-2 px-4 py-2 bg-veil-600 hover:bg-veil-700 rounded text-sm font-medium transition-colors disabled:opacity-40"
          >
            <Upload className="w-4 h-4" />
            {activating ? 'Activating...' : 'Activate License'}
          </button>
        </div>
      )}
    </section>
  )
}

function ApiKeysSection() {
  const [keys, setKeys] = useState<ApiKeyData[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [newKey, setNewKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')

  const load = () => api.getApiKeys().then(setKeys).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    setError('')
    if (!name.trim()) { setError('Name is required'); return }
    try {
      const result = await api.createApiKey({ name: name.trim() })
      setNewKey(result.key)
      setName('')
      setShowCreate(false)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleRevoke = async (key: ApiKeyData) => {
    if (!window.confirm('Delete this API key? This cannot be undone.')) return
    try {
      await api.revokeApiKey(key.id)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const copyKey = () => {
    if (newKey) {
      navigator.clipboard.writeText(newKey)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <section className="border-t border-gray-800 pt-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Key className="w-4 h-4 text-gray-400" />
          <h2 className="text-lg font-semibold">VeilProxy API Keys</h2>
        </div>
        <button onClick={() => { setShowCreate(true); setNewKey(null); setError('') }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors">
          <Plus className="w-4 h-4" /> Create Key
        </button>
      </div>
      <p className="text-sm text-gray-400 mb-4">
        Use these keys to authenticate with the VeilProxy gateway API at <code className="text-xs bg-gray-800 px-1.5 py-0.5 rounded">/v1/chat/completions</code>
      </p>

      {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

      {/* New key warning */}
      {newKey && (
        <div className="bg-amber-900/20 border border-amber-700/50 rounded-lg p-3 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-medium text-amber-300">Save this key — it won't be shown again</span>
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs bg-gray-900 px-3 py-2 rounded font-mono text-green-400 overflow-x-auto">{newKey}</code>
            <button onClick={copyKey} className="p-2 rounded hover:bg-gray-800 transition-colors shrink-0">
              {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4 text-gray-400" />}
            </button>
          </div>
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-3 mb-4 flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs text-gray-400 mb-1">Key Name</label>
            <input value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. Production, CI/CD"
              className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm"
              onKeyDown={e => e.key === 'Enter' && handleCreate()} />
          </div>
          <button onClick={handleCreate} className="px-4 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors">Create</button>
          <button onClick={() => setShowCreate(false)} className="px-3 py-1.5 text-gray-400 hover:text-white text-sm">Cancel</button>
        </div>
      )}

      {/* Keys table */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800">
            <tr>
              <th className="text-left p-3 text-gray-400 font-medium">Name</th>
              <th className="text-left p-3 text-gray-400 font-medium">Key</th>
              <th className="text-center p-3 text-gray-400 font-medium">Status</th>
              <th className="text-left p-3 text-gray-400 font-medium">Last Used</th>
              <th className="text-left p-3 text-gray-400 font-medium">Created</th>
              <th className="text-right p-3 text-gray-400 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 ? (
              <tr><td colSpan={6} className="p-4 text-center text-gray-500">No API keys created yet</td></tr>
            ) : keys.map((key) => (
              <tr key={key.id} className="border-t border-gray-700/50">
                <td className="p-3 font-medium">{key.name}</td>
                <td className="p-3 font-mono text-xs text-gray-400">{key.key_prefix}...{'*'.repeat(20)}</td>
                <td className="p-3 text-center">
                  <span className={`px-2 py-0.5 rounded text-xs ${key.is_active ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
                    {key.is_active ? 'active' : 'revoked'}
                  </span>
                </td>
                <td className="p-3 text-xs text-gray-400">{key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}</td>
                <td className="p-3 text-xs text-gray-400">{new Date(key.created_at).toLocaleDateString()}</td>
                <td className="p-3 text-right">
                  {key.is_active && (
                    <button onClick={() => handleRevoke(key)} className="p-1 rounded hover:bg-gray-700" title="Revoke key">
                      <Trash2 className="w-3.5 h-3.5 text-red-400" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
