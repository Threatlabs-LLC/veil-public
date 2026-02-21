import { useEffect, useState } from 'react'
import { Webhook, Plus, Trash2, X, Zap, AlertTriangle, Check, Pencil, Power } from 'lucide-react'
import { api } from '../api/client'
import type { WebhookData } from '../api/client'

const EVENT_TYPES = [
  'entity.detected',
  'policy.violation',
  'request.high_risk',
  'usage.threshold',
  'auth.failure',
  'provider.error',
]

interface WebhookFormData {
  name: string
  url: string
  format: string
  event_types: string[]
}

const emptyForm: WebhookFormData = { name: '', url: '', format: 'json', event_types: [] }

export default function Webhooks() {
  const [webhooks, setWebhooks] = useState<WebhookData[]>([])
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<WebhookData | null>(null)
  const [form, setForm] = useState<WebhookFormData>(emptyForm)
  const [error, setError] = useState('')
  const [testStatus, setTestStatus] = useState<Record<string, string>>({})

  const load = () => api.getWebhooks().then(setWebhooks).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const openCreate = () => {
    setForm(emptyForm)
    setEditing(null)
    setShowForm(true)
    setError('')
  }

  const openEdit = (wh: WebhookData) => {
    setForm({
      name: wh.name,
      url: wh.url,
      format: wh.format,
      event_types: [...wh.event_types],
    })
    setEditing(wh)
    setShowForm(true)
    setError('')
  }

  const handleSubmit = async () => {
    setError('')
    if (!form.name.trim() || !form.url.trim()) {
      setError('Name and URL are required')
      return
    }
    try {
      if (editing) {
        await api.updateWebhook(editing.id, {
          name: form.name.trim(),
          url: form.url.trim(),
          event_types: form.event_types,
          format: form.format,
        })
      } else {
        await api.createWebhook({
          name: form.name.trim(),
          url: form.url.trim(),
          event_types: form.event_types,
          format: form.format,
        })
      }
      setShowForm(false)
      setEditing(null)
      setForm(emptyForm)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleDelete = async (webhook: WebhookData) => {
    if (!window.confirm('Delete this webhook? This cannot be undone.')) return
    try {
      await api.deleteWebhook(webhook.id)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleToggleActive = async (webhook: WebhookData) => {
    try {
      await api.updateWebhook(webhook.id, { is_active: !webhook.is_active })
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleTest = async (webhook: WebhookData) => {
    setTestStatus(prev => ({ ...prev, [webhook.id]: 'sending' }))
    try {
      await api.testWebhook(webhook.id)
      setTestStatus(prev => ({ ...prev, [webhook.id]: 'success' }))
      setTimeout(() => setTestStatus(prev => ({ ...prev, [webhook.id]: '' })), 3000)
    } catch (e) {
      setTestStatus(prev => ({ ...prev, [webhook.id]: (e as Error).message }))
      setTimeout(() => setTestStatus(prev => ({ ...prev, [webhook.id]: '' })), 5000)
    }
  }

  const toggleEvent = (et: string) => {
    setForm(prev => ({
      ...prev,
      event_types: prev.event_types.includes(et)
        ? prev.event_types.filter(e => e !== et)
        : [...prev.event_types, et],
    }))
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <header className="h-14 border-b border-gray-800 flex items-center px-4 gap-4">
        <Webhook className="w-5 h-5 text-veil-500" />
        <span className="font-medium">Webhooks</span>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Webhook Endpoints</h2>
              <p className="text-sm text-gray-400 mt-0.5">
                Receive real-time notifications when VeilProxy detects PII, policy violations, or other events.
              </p>
            </div>
            <button
              onClick={openCreate}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors"
            >
              <Plus className="w-4 h-4" /> Add Webhook
            </button>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          {/* Create/Edit form */}
          {showForm && (
            <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-medium">{editing ? 'Edit Webhook' : 'New Webhook'}</h3>
                <button onClick={() => { setShowForm(false); setEditing(null) }}><X className="w-4 h-4 text-gray-400" /></button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Name</label>
                  <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                    placeholder="e.g. Slack Alerts"
                    className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Format</label>
                  <select value={form.format} onChange={e => setForm({ ...form, format: e.target.value })}
                    className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm">
                    <option value="json">JSON</option>
                    <option value="slack">Slack Block Kit</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">URL</label>
                <input value={form.url} onChange={e => setForm({ ...form, url: e.target.value })}
                  placeholder="https://hooks.slack.com/services/..."
                  className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm font-mono" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Event Types (empty = all)</label>
                <div className="flex flex-wrap gap-2 mt-1">
                  {EVENT_TYPES.map(et => (
                    <button
                      key={et}
                      onClick={() => toggleEvent(et)}
                      className={`px-2 py-1 rounded text-xs transition-colors ${
                        form.event_types.includes(et)
                          ? 'bg-veil-600 text-white'
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                      }`}
                    >
                      {et}
                    </button>
                  ))}
                </div>
              </div>
              <button onClick={handleSubmit}
                className="px-4 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors">
                {editing ? 'Save Changes' : 'Create Webhook'}
              </button>
            </div>
          )}

          {/* Webhook list */}
          <div className="space-y-3">
            {webhooks.length === 0 && !showForm && (
              <div className="text-center text-gray-500 py-12">
                <Webhook className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p>No webhooks configured yet</p>
                <p className="text-xs mt-1">Create one to start receiving real-time notifications</p>
              </div>
            )}

            {webhooks.map(wh => (
              <div key={wh.id} className="bg-gray-800/50 border border-gray-700 rounded-xl p-4 group">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${wh.is_active ? 'bg-green-500' : 'bg-gray-600'}`} />
                      <span className="font-medium">{wh.name}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase ${
                        wh.format === 'slack' ? 'bg-purple-900/50 text-purple-300' : 'bg-blue-900/50 text-blue-300'
                      }`}>
                        {wh.format}
                      </span>
                    </div>
                    <div className="text-xs font-mono text-gray-400 mt-1 truncate">{wh.url}</div>
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                      {wh.event_types.length > 0 ? (
                        <span>{wh.event_types.join(', ')}</span>
                      ) : (
                        <span>All events</span>
                      )}
                      {wh.failure_count > 0 && (
                        <span className="flex items-center gap-1 text-amber-400">
                          <AlertTriangle className="w-3 h-3" />
                          {wh.failure_count} failures
                        </span>
                      )}
                      {wh.last_triggered_at && (
                        <span>Last fired: {new Date(wh.last_triggered_at).toLocaleString()}</span>
                      )}
                    </div>
                    {wh.last_error && (
                      <div className="text-xs text-red-400 mt-1 truncate">Last error: {wh.last_error}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-1 ml-4">
                    <button
                      onClick={() => handleTest(wh)}
                      disabled={testStatus[wh.id] === 'sending'}
                      className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-gray-700 hover:bg-gray-600 transition-colors disabled:opacity-50"
                    >
                      {testStatus[wh.id] === 'sending' ? (
                        <span>Sending...</span>
                      ) : testStatus[wh.id] === 'success' ? (
                        <><Check className="w-3 h-3 text-green-400" /> Sent</>
                      ) : (
                        <><Zap className="w-3 h-3" /> Test</>
                      )}
                    </button>
                    <button
                      onClick={() => handleToggleActive(wh)}
                      className="p-1 rounded hover:bg-gray-700 transition-colors opacity-0 group-hover:opacity-100"
                      title={wh.is_active ? 'Disable' : 'Enable'}
                    >
                      <Power className={`w-3.5 h-3.5 ${wh.is_active ? 'text-green-400' : 'text-gray-500'}`} />
                    </button>
                    <button
                      onClick={() => openEdit(wh)}
                      className="p-1 rounded hover:bg-gray-700 transition-colors opacity-0 group-hover:opacity-100"
                      title="Edit"
                    >
                      <Pencil className="w-3.5 h-3.5 text-gray-400" />
                    </button>
                    <button
                      onClick={() => handleDelete(wh)}
                      className="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                      title="Delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                {testStatus[wh.id] && testStatus[wh.id] !== 'sending' && testStatus[wh.id] !== 'success' && (
                  <div className="text-xs text-red-400 mt-2">{testStatus[wh.id]}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
