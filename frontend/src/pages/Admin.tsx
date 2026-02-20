import { useEffect, useState } from 'react'
import {
  Activity, Users, FileText, AlertTriangle, BarChart3,
  Database, Eye, Clock, TrendingUp,
  Plus, Pencil, Trash2, X, Power, UserPlus, Copy, Check
} from 'lucide-react'
import { api } from '../api/client'
import type { DashboardStats, UsageData, AuditLogEntry, DetectionRule, PolicyData } from '../api/client'

type Tab = 'overview' | 'usage' | 'rules' | 'policies' | 'users' | 'audit'

const TIER_FEATURES: Record<string, string[]> = {
  free: [],
  solo: ['custom_rules'],
  team: ['custom_rules', 'webhooks', 'multi_provider', 'advanced_audit', 'sso'],
  business: ['custom_rules', 'webhooks', 'multi_provider', 'advanced_audit', 'sso', 'api_keys'],
  enterprise: ['custom_rules', 'webhooks', 'multi_provider', 'advanced_audit', 'sso', 'api_keys'],
}

export default function Admin() {
  const [tab, setTab] = useState<Tab>('overview')
  const [visibleTabs, setVisibleTabs] = useState<Tab[]>(['overview', 'usage', 'rules', 'policies'])

  useEffect(() => {
    const user = JSON.parse(localStorage.getItem('veilchat_user') || '{}')
    const isAdmin = user.role === 'owner' || user.role === 'admin'
    const tabs: Tab[] = ['overview', 'usage', 'rules', 'policies']
    if (isAdmin) tabs.push('users')
    api.getQuota().then((q) => {
      const features = TIER_FEATURES[q.tier] || []
      if (features.includes('advanced_audit')) tabs.push('audit')
      setVisibleTabs(tabs)
    }).catch(() => {
      setVisibleTabs(tabs)
    })
  }, [])

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Header */}
      <header className="h-14 border-b border-gray-800 flex items-center px-4 gap-4">
        <BarChart3 className="w-5 h-5 text-veil-500" />
        <span className="font-medium">Admin Dashboard</span>
        <nav className="flex gap-1 ml-4">
          {visibleTabs.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded text-sm capitalize transition-colors ${
                tab === t ? 'bg-veil-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              {t}
            </button>
          ))}
        </nav>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {tab === 'overview' && <OverviewTab />}
        {tab === 'usage' && <UsageTab />}
        {tab === 'rules' && <RulesTab />}
        {tab === 'policies' && <PoliciesTab />}
        {tab === 'users' && <UsersTab />}
        {tab === 'audit' && <AuditTab />}
      </div>
    </div>
  )
}

function StatCard({ label, value, icon: Icon, color = 'text-veil-500' }: {
  label: string; value: string | number; icon: typeof BarChart3; color?: string
}) {
  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-400">{label}</span>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  )
}

function OverviewTab() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getDashboard().then(setStats).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="text-red-400">{error}</div>
  if (!stats) return <div className="text-gray-500">Loading...</div>

  return (
    <div className="space-y-6 max-w-5xl">
      <h2 className="text-lg font-semibold">Overview</h2>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Conversations" value={stats.total_conversations} icon={Activity} />
        <StatCard label="Messages" value={stats.total_messages} icon={FileText} />
        <StatCard label="Entities Detected" value={stats.total_entities_detected} icon={Eye} color="text-amber-500" />
        <StatCard label="Active Users" value={stats.active_users} icon={Users} color="text-green-500" />
        <StatCard label="Tokens Used" value={stats.total_tokens_used.toLocaleString()} icon={Database} />
        <StatCard label="Est. Cost" value={`$${stats.estimated_cost_usd.toFixed(2)}`} icon={TrendingUp} color="text-emerald-500" />
        <StatCard label="Requests Today" value={stats.requests_today} icon={Clock} />
        <StatCard label="Entities Today" value={stats.entities_today} icon={AlertTriangle} color="text-amber-500" />
      </div>

      {stats.top_entity_types.length > 0 && (
        <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Top Entity Types</h3>
          <div className="space-y-2">
            {stats.top_entity_types.map((t) => (
              <div key={t.type} className="flex items-center justify-between">
                <span className="text-sm font-mono">{t.type}</span>
                <div className="flex items-center gap-2">
                  <div className="w-32 bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-veil-500 h-2 rounded-full"
                      style={{
                        width: `${Math.min(100, (t.count / Math.max(...stats.top_entity_types.map(x => x.count))) * 100)}%`
                      }}
                    />
                  </div>
                  <span className="text-sm text-gray-400 w-12 text-right">{t.count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function UsageTab() {
  const [usage, setUsage] = useState<UsageData | null>(null)
  const [days, setDays] = useState(30)
  const [groupBy, setGroupBy] = useState('day')
  const [error, setError] = useState('')

  useEffect(() => {
    setError('')
    api.getUsage(days, groupBy).then(setUsage).catch((e) => setError(e.message))
  }, [days, groupBy])

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-semibold">Usage Analytics</h2>
        {error && <span className="text-red-400 text-sm">{error}</span>}
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm"
        >
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
          <option value={90}>90 days</option>
        </select>
        <select
          value={groupBy}
          onChange={(e) => setGroupBy(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm"
        >
          <option value="day">By Day</option>
          <option value="provider">By Provider</option>
          <option value="model">By Model</option>
        </select>
      </div>

      {usage && (
        <div className="bg-gray-800/50 border border-gray-700 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-800">
              <tr>
                <th className="text-left p-3 text-gray-400 font-medium">{groupBy === 'day' ? 'Date' : 'Group'}</th>
                <th className="text-right p-3 text-gray-400 font-medium">Requests</th>
                <th className="text-right p-3 text-gray-400 font-medium">Tokens</th>
                <th className="text-right p-3 text-gray-400 font-medium">Cost</th>
                <th className="text-right p-3 text-gray-400 font-medium">Entities</th>
                <th className="text-right p-3 text-gray-400 font-medium">Errors</th>
              </tr>
            </thead>
            <tbody>
              {usage.data.length === 0 ? (
                <tr><td colSpan={6} className="p-4 text-center text-gray-500">No usage data yet</td></tr>
              ) : usage.data.map((row, i) => (
                <tr key={i} className="border-t border-gray-700/50">
                  <td className="p-3 font-mono">{row.group}</td>
                  <td className="p-3 text-right">{row.request_count}</td>
                  <td className="p-3 text-right">{row.total_tokens.toLocaleString()}</td>
                  <td className="p-3 text-right text-emerald-400">${row.estimated_cost_usd.toFixed(4)}</td>
                  <td className="p-3 text-right text-amber-400">{row.entities_detected}</td>
                  <td className="p-3 text-right text-red-400">{row.error_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// --- Rules Tab with CRUD ---

interface RuleFormData {
  name: string
  description: string
  entity_type: string
  detection_method: string
  pattern: string
  word_list: string
  priority: number
  confidence: number
}

const emptyRuleForm: RuleFormData = {
  name: '', description: '', entity_type: '', detection_method: 'regex',
  pattern: '', word_list: '', priority: 100, confidence: 0.8,
}

function RulesTab() {
  const [rules, setRules] = useState<DetectionRule[]>([])
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<DetectionRule | null>(null)
  const [form, setForm] = useState<RuleFormData>(emptyRuleForm)
  const [error, setError] = useState('')

  const load = () => api.getRules().then(setRules).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const openCreate = () => {
    setForm(emptyRuleForm)
    setEditing(null)
    setShowForm(true)
    setError('')
  }

  const openEdit = (rule: DetectionRule) => {
    setForm({
      name: rule.name,
      description: rule.description || '',
      entity_type: rule.entity_type,
      detection_method: rule.detection_method,
      pattern: rule.pattern || '',
      word_list: rule.word_list ? rule.word_list.join(', ') : '',
      priority: rule.priority,
      confidence: rule.confidence,
    })
    setEditing(rule)
    setShowForm(true)
    setError('')
  }

  const handleSubmit = async () => {
    setError('')
    try {
      if (editing) {
        await api.updateRule(editing.id, {
          name: form.name,
          description: form.description || null,
          pattern: form.detection_method === 'regex' ? form.pattern : null,
          word_list: form.detection_method === 'dictionary'
            ? form.word_list.split(',').map(w => w.trim()).filter(Boolean)
            : null,
          priority: form.priority,
          confidence: form.confidence,
        })
      } else {
        await api.createRule({
          name: form.name,
          entity_type: form.entity_type,
          detection_method: form.detection_method,
          description: form.description || undefined,
          pattern: form.detection_method === 'regex' ? form.pattern : undefined,
          word_list: form.detection_method === 'dictionary'
            ? form.word_list.split(',').map(w => w.trim()).filter(Boolean)
            : undefined,
          priority: form.priority,
          confidence: form.confidence,
        })
      }
      setShowForm(false)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleDelete = async (rule: DetectionRule) => {
    if (!confirm(`Delete rule "${rule.name}"?`)) return
    try {
      await api.deleteRule(rule.id)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const toggleActive = async (rule: DetectionRule) => {
    try {
      await api.updateRule(rule.id, { is_active: !rule.is_active })
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Detection Rules</h2>
        <button onClick={openCreate} className="flex items-center gap-1.5 px-3 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors">
          <Plus className="w-4 h-4" /> Add Rule
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Create/Edit Form */}
      {showForm && (
        <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">{editing ? 'Edit Rule' : 'Create Rule'}</h3>
            <button onClick={() => setShowForm(false)}><X className="w-4 h-4 text-gray-400" /></button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Name</label>
              <input value={form.name} onChange={e => setForm({...form, name: e.target.value})}
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Entity Type</label>
              <input list="entity-type-options" value={form.entity_type} onChange={e => setForm({...form, entity_type: e.target.value.toUpperCase().replace(/\s+/g, '_')})}
                disabled={!!editing} placeholder="e.g. ORGANIZATION, COMPANY_NAME"
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm disabled:opacity-50" />
              <datalist id="entity-type-options">
                <option value="PERSON" />
                <option value="ORGANIZATION" />
                <option value="COMPANY_NAME" />
                <option value="EMAIL" />
                <option value="PHONE" />
                <option value="IP_ADDRESS" />
                <option value="CREDIT_CARD" />
                <option value="SSN" />
                <option value="AWS_KEY" />
                <option value="HOSTNAME" />
                <option value="CONNECTION_STRING" />
                <option value="MAC_ADDRESS" />
                <option value="DATE_OF_BIRTH" />
                <option value="ADDRESS" />
                <option value="API_KEY" />
                <option value="PROJECT_NAME" />
                <option value="INTERNAL_ID" />
                <option value="CUSTOM_SECRET" />
              </datalist>
              <span className="text-xs text-gray-500">Select or type a custom entity type</span>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Method</label>
              <select value={form.detection_method} onChange={e => setForm({...form, detection_method: e.target.value})}
                disabled={!!editing}
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm disabled:opacity-50">
                <option value="regex">Regex</option>
                <option value="dictionary">Dictionary</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Priority</label>
              <input type="number" value={form.priority} onChange={e => setForm({...form, priority: parseInt(e.target.value) || 0})}
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
            </div>
          </div>
          {form.detection_method === 'regex' ? (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Regex Pattern</label>
              <input value={form.pattern} onChange={e => setForm({...form, pattern: e.target.value})}
                placeholder="\b[A-Z0-9]+\b" className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm font-mono" />
            </div>
          ) : (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Word List (comma-separated)</label>
              <input value={form.word_list} onChange={e => setForm({...form, word_list: e.target.value})}
                placeholder="secret, confidential, internal" className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
            </div>
          )}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Description</label>
            <input value={form.description} onChange={e => setForm({...form, description: e.target.value})}
              className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Confidence: {(form.confidence * 100).toFixed(0)}%</label>
            <input type="range" min="0.1" max="1" step="0.05" value={form.confidence}
              onChange={e => setForm({...form, confidence: parseFloat(e.target.value)})}
              className="w-full accent-veil-500" />
          </div>
          <button onClick={handleSubmit} className="px-4 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors">
            {editing ? 'Save Changes' : 'Create Rule'}
          </button>
        </div>
      )}

      <div className="bg-gray-800/50 border border-gray-700 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800">
            <tr>
              <th className="text-left p-3 text-gray-400 font-medium">Name</th>
              <th className="text-left p-3 text-gray-400 font-medium">Entity Type</th>
              <th className="text-left p-3 text-gray-400 font-medium">Method</th>
              <th className="text-right p-3 text-gray-400 font-medium">Priority</th>
              <th className="text-right p-3 text-gray-400 font-medium">Confidence</th>
              <th className="text-center p-3 text-gray-400 font-medium">Status</th>
              <th className="text-right p-3 text-gray-400 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 ? (
              <tr><td colSpan={7} className="p-4 text-center text-gray-500">No rules configured</td></tr>
            ) : rules.map((rule) => (
              <tr key={rule.id} className="border-t border-gray-700/50 group">
                <td className="p-3">
                  <div className="font-medium">{rule.name}</div>
                  {rule.description && <div className="text-gray-500 text-xs mt-0.5">{rule.description}</div>}
                </td>
                <td className="p-3 font-mono text-xs">{rule.entity_type}</td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    rule.detection_method === 'regex' ? 'bg-blue-900/50 text-blue-300' : 'bg-purple-900/50 text-purple-300'
                  }`}>
                    {rule.detection_method}
                  </span>
                </td>
                <td className="p-3 text-right">{rule.priority}</td>
                <td className="p-3 text-right">{(rule.confidence * 100).toFixed(0)}%</td>
                <td className="p-3 text-center">
                  <span className={`inline-block w-2 h-2 rounded-full ${rule.is_active ? 'bg-green-500' : 'bg-gray-600'}`} />
                </td>
                <td className="p-3 text-right">
                  {!rule.is_built_in && (
                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => toggleActive(rule)} className="p-1 rounded hover:bg-gray-700" title={rule.is_active ? 'Disable' : 'Enable'}>
                        <Power className={`w-3.5 h-3.5 ${rule.is_active ? 'text-green-400' : 'text-gray-500'}`} />
                      </button>
                      <button onClick={() => openEdit(rule)} className="p-1 rounded hover:bg-gray-700" title="Edit">
                        <Pencil className="w-3.5 h-3.5 text-gray-400" />
                      </button>
                      <button onClick={() => handleDelete(rule)} className="p-1 rounded hover:bg-gray-700" title="Delete">
                        <Trash2 className="w-3.5 h-3.5 text-red-400" />
                      </button>
                    </div>
                  )}
                  {rule.is_built_in && <span className="text-xs text-gray-600">built-in</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// --- Policies Tab with CRUD ---

interface PolicyFormData {
  name: string
  description: string
  entity_type: string
  action: string
  severity: string
  notify: boolean
  min_confidence: number
  priority: number
}

const emptyPolicyForm: PolicyFormData = {
  name: '', description: '', entity_type: '*', action: 'redact',
  severity: 'medium', notify: false, min_confidence: 0.7, priority: 100,
}

function PoliciesTab() {
  const [policies, setPolicies] = useState<PolicyData[]>([])
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<PolicyData | null>(null)
  const [form, setForm] = useState<PolicyFormData>(emptyPolicyForm)
  const [error, setError] = useState('')

  const load = () => api.getPolicies().then(setPolicies).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const openCreate = () => {
    setForm(emptyPolicyForm)
    setEditing(null)
    setShowForm(true)
    setError('')
  }

  const openEdit = (policy: PolicyData) => {
    setForm({
      name: policy.name,
      description: policy.description || '',
      entity_type: policy.entity_type,
      action: policy.action,
      severity: policy.severity,
      notify: policy.notify,
      min_confidence: policy.min_confidence,
      priority: policy.priority,
    })
    setEditing(policy)
    setShowForm(true)
    setError('')
  }

  const handleSubmit = async () => {
    setError('')
    try {
      if (editing) {
        await api.updatePolicy(editing.id, {
          name: form.name,
          description: form.description || null,
          action: form.action,
          severity: form.severity,
          notify: form.notify,
          min_confidence: form.min_confidence,
          priority: form.priority,
        })
      } else {
        await api.createPolicy({
          name: form.name,
          entity_type: form.entity_type,
          action: form.action,
          description: form.description || undefined,
          severity: form.severity,
          notify: form.notify,
          min_confidence: form.min_confidence,
          priority: form.priority,
        })
      }
      setShowForm(false)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleDelete = async (policy: PolicyData) => {
    if (!confirm(`Delete policy "${policy.name}"?`)) return
    try {
      await api.deletePolicy(policy.id)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const toggleActive = async (policy: PolicyData) => {
    try {
      await api.updatePolicy(policy.id, { is_active: !policy.is_active })
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const actionColors: Record<string, string> = {
    block: 'bg-red-900/50 text-red-300',
    warn: 'bg-amber-900/50 text-amber-300',
    redact: 'bg-blue-900/50 text-blue-300',
    allow: 'bg-green-900/50 text-green-300',
  }

  const severityColors: Record<string, string> = {
    critical: 'text-red-400',
    high: 'text-orange-400',
    medium: 'text-amber-400',
    low: 'text-gray-400',
  }

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Policies</h2>
          <p className="text-sm text-gray-400 mt-0.5">
            Policies define what happens when PII is detected. Evaluated in priority order — first match wins.
          </p>
        </div>
        <button onClick={openCreate} className="flex items-center gap-1.5 px-3 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors">
          <Plus className="w-4 h-4" /> Add Policy
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Create/Edit Form */}
      {showForm && (
        <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">{editing ? 'Edit Policy' : 'Create Policy'}</h3>
            <button onClick={() => setShowForm(false)}><X className="w-4 h-4 text-gray-400" /></button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Name</label>
              <input value={form.name} onChange={e => setForm({...form, name: e.target.value})}
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Entity Type (* = all)</label>
              <input value={form.entity_type} onChange={e => setForm({...form, entity_type: e.target.value})}
                disabled={!!editing} placeholder="EMAIL, PERSON, *, etc."
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm disabled:opacity-50" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Action</label>
              <select value={form.action} onChange={e => setForm({...form, action: e.target.value})}
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm">
                <option value="redact">Redact</option>
                <option value="block">Block</option>
                <option value="warn">Warn</option>
                <option value="allow">Allow</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Severity</label>
              <select value={form.severity} onChange={e => setForm({...form, severity: e.target.value})}
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Priority</label>
              <input type="number" value={form.priority} onChange={e => setForm({...form, priority: parseInt(e.target.value) || 0})}
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
            </div>
            <div className="flex items-center gap-2 pt-5">
              <input type="checkbox" checked={form.notify} onChange={e => setForm({...form, notify: e.target.checked})}
                className="w-4 h-4 rounded border-gray-600 bg-gray-900" />
              <label className="text-sm">Send notification</label>
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Description</label>
            <input value={form.description} onChange={e => setForm({...form, description: e.target.value})}
              className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Min Confidence: {(form.min_confidence * 100).toFixed(0)}%</label>
            <input type="range" min="0.1" max="1" step="0.05" value={form.min_confidence}
              onChange={e => setForm({...form, min_confidence: parseFloat(e.target.value)})}
              className="w-full accent-veil-500" />
          </div>
          <button onClick={handleSubmit} className="px-4 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors">
            {editing ? 'Save Changes' : 'Create Policy'}
          </button>
        </div>
      )}

      <div className="bg-gray-800/50 border border-gray-700 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800">
            <tr>
              <th className="text-left p-3 text-gray-400 font-medium">Name</th>
              <th className="text-left p-3 text-gray-400 font-medium">Entity Type</th>
              <th className="text-center p-3 text-gray-400 font-medium">Action</th>
              <th className="text-center p-3 text-gray-400 font-medium">Severity</th>
              <th className="text-right p-3 text-gray-400 font-medium">Min Conf.</th>
              <th className="text-right p-3 text-gray-400 font-medium">Priority</th>
              <th className="text-center p-3 text-gray-400 font-medium">Active</th>
              <th className="text-right p-3 text-gray-400 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {policies.length === 0 ? (
              <tr><td colSpan={8} className="p-4 text-center text-gray-500">No policies configured</td></tr>
            ) : policies.map((p) => (
              <tr key={p.id} className="border-t border-gray-700/50 group">
                <td className="p-3">
                  <div className="font-medium">{p.name}</div>
                  {p.description && <div className="text-gray-500 text-xs mt-0.5">{p.description}</div>}
                </td>
                <td className="p-3 font-mono text-xs">{p.entity_type}</td>
                <td className="p-3 text-center">
                  <span className={`px-2 py-0.5 rounded text-xs uppercase ${actionColors[p.action] || 'bg-gray-700'}`}>
                    {p.action}
                  </span>
                </td>
                <td className={`p-3 text-center text-xs font-medium ${severityColors[p.severity] || ''}`}>
                  {p.severity}
                </td>
                <td className="p-3 text-right">{(p.min_confidence * 100).toFixed(0)}%</td>
                <td className="p-3 text-right">{p.priority}</td>
                <td className="p-3 text-center">
                  <span className={`inline-block w-2 h-2 rounded-full ${p.is_active ? 'bg-green-500' : 'bg-gray-600'}`} />
                </td>
                <td className="p-3 text-right">
                  {!p.is_built_in && (
                    <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => toggleActive(p)} className="p-1 rounded hover:bg-gray-700" title={p.is_active ? 'Disable' : 'Enable'}>
                        <Power className={`w-3.5 h-3.5 ${p.is_active ? 'text-green-400' : 'text-gray-500'}`} />
                      </button>
                      <button onClick={() => openEdit(p)} className="p-1 rounded hover:bg-gray-700" title="Edit">
                        <Pencil className="w-3.5 h-3.5 text-gray-400" />
                      </button>
                      <button onClick={() => handleDelete(p)} className="p-1 rounded hover:bg-gray-700" title="Delete">
                        <Trash2 className="w-3.5 h-3.5 text-red-400" />
                      </button>
                    </div>
                  )}
                  {p.is_built_in && <span className="text-xs text-gray-600">built-in</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

interface UserData {
  id: string; email: string; display_name: string | null; role: string;
  is_active: boolean; last_login_at: string | null; created_at: string;
}

function UsersTab() {
  const [users, setUsers] = useState<UserData[]>([])
  const [showInvite, setShowInvite] = useState(false)
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [role, setRole] = useState('member')
  const [error, setError] = useState('')
  const [inviteResult, setInviteResult] = useState<{ email: string; temp_password: string } | null>(null)
  const [copied, setCopied] = useState(false)

  const load = () => api.getUsers().then(setUsers).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const handleInvite = async () => {
    setError('')
    if (!email.trim()) { setError('Email is required'); return }
    try {
      const result = await api.inviteUser({
        email: email.trim(),
        role,
        display_name: displayName.trim() || undefined,
      })
      setInviteResult({ email: result.email, temp_password: result.temp_password })
      setEmail('')
      setDisplayName('')
      setRole('member')
      setShowInvite(false)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleRoleChange = async (user: UserData, newRole: string) => {
    try {
      await api.updateUser(user.id, { role: newRole })
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleToggleActive = async (user: UserData) => {
    const action = user.is_active ? 'deactivate' : 'reactivate'
    if (!confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} user "${user.email}"?`)) return
    try {
      await api.updateUser(user.id, { is_active: !user.is_active })
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const roleColors: Record<string, string> = {
    owner: 'bg-amber-900/50 text-amber-300',
    admin: 'bg-veil-900/50 text-veil-300',
    member: 'bg-gray-700 text-gray-300',
  }

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Team Members</h2>
        <button onClick={() => { setShowInvite(true); setError(''); setInviteResult(null) }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors">
          <UserPlus className="w-4 h-4" /> Invite User
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Invite result — show temp password */}
      {inviteResult && (
        <div className="bg-green-900/20 border border-green-700/50 rounded-lg p-3">
          <p className="text-sm text-green-300 mb-2">
            Invited <strong>{inviteResult.email}</strong> — share this temporary password securely:
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs bg-gray-900 px-3 py-2 rounded font-mono text-green-400">{inviteResult.temp_password}</code>
            <button onClick={() => {
              navigator.clipboard.writeText(inviteResult.temp_password)
              setCopied(true)
              setTimeout(() => setCopied(false), 2000)
            }} className="p-2 rounded hover:bg-gray-800 transition-colors shrink-0">
              {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4 text-gray-400" />}
            </button>
          </div>
        </div>
      )}

      {/* Invite form */}
      {showInvite && (
        <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-medium">Invite New User</h3>
            <button onClick={() => setShowInvite(false)}><X className="w-4 h-4 text-gray-400" /></button>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Email</label>
              <input value={email} onChange={e => setEmail(e.target.value)}
                placeholder="user@company.com"
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Display Name</label>
              <input value={displayName} onChange={e => setDisplayName(e.target.value)}
                placeholder="Jane Doe"
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Role</label>
              <select value={role} onChange={e => setRole(e.target.value)}
                className="w-full px-2 py-1.5 bg-gray-900 border border-gray-700 rounded text-sm">
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <button onClick={handleInvite}
            className="px-4 py-1.5 bg-veil-600 hover:bg-veil-700 rounded text-sm transition-colors">
            Send Invite
          </button>
        </div>
      )}

      {/* Users table */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800">
            <tr>
              <th className="text-left p-3 text-gray-400 font-medium">User</th>
              <th className="text-left p-3 text-gray-400 font-medium">Email</th>
              <th className="text-center p-3 text-gray-400 font-medium">Role</th>
              <th className="text-center p-3 text-gray-400 font-medium">Status</th>
              <th className="text-left p-3 text-gray-400 font-medium">Last Login</th>
              <th className="text-left p-3 text-gray-400 font-medium">Joined</th>
              <th className="text-right p-3 text-gray-400 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-gray-700/50 group">
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-veil-600/50 flex items-center justify-center text-xs font-bold">
                      {(u.display_name ?? u.email).charAt(0).toUpperCase()}
                    </div>
                    <span className="font-medium">{u.display_name || '-'}</span>
                  </div>
                </td>
                <td className="p-3 text-gray-300">{u.email}</td>
                <td className="p-3 text-center">
                  <select
                    value={u.role}
                    onChange={(e) => handleRoleChange(u, e.target.value)}
                    className={`px-2 py-0.5 rounded text-xs border-0 cursor-pointer ${roleColors[u.role] || 'bg-gray-700'}`}
                  >
                    <option value="member">member</option>
                    <option value="admin">admin</option>
                    <option value="owner">owner</option>
                  </select>
                </td>
                <td className="p-3 text-center">
                  <span className={`px-2 py-0.5 rounded text-xs ${u.is_active ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
                    {u.is_active ? 'active' : 'disabled'}
                  </span>
                </td>
                <td className="p-3 text-xs text-gray-400">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : 'Never'}
                </td>
                <td className="p-3 text-xs text-gray-400">
                  {new Date(u.created_at).toLocaleDateString()}
                </td>
                <td className="p-3 text-right">
                  <button
                    onClick={() => handleToggleActive(u)}
                    className="p-1 rounded hover:bg-gray-700 opacity-0 group-hover:opacity-100 transition-opacity"
                    title={u.is_active ? 'Deactivate' : 'Activate'}
                  >
                    <Power className={`w-3.5 h-3.5 ${u.is_active ? 'text-green-400' : 'text-red-400'}`} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AuditTab() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getAuditLogs(100).then((data) => {
      setLogs(data.logs)
      setTotal(data.total)
    }).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="space-y-4 max-w-5xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Audit Logs</h2>
        <span className="text-sm text-gray-500">{total} entries</span>
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <div className="bg-gray-800/50 border border-gray-700 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-800">
            <tr>
              <th className="text-left p-3 text-gray-400 font-medium">Time</th>
              <th className="text-left p-3 text-gray-400 font-medium">Event</th>
              <th className="text-left p-3 text-gray-400 font-medium">Engine</th>
              <th className="text-left p-3 text-gray-400 font-medium">Model</th>
              <th className="text-right p-3 text-gray-400 font-medium">Latency</th>
              <th className="text-left p-3 text-gray-400 font-medium">Error</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr><td colSpan={6} className="p-4 text-center text-gray-500">No audit logs yet</td></tr>
            ) : logs.map((log) => {
              const isSanitize = log.event_type.includes('sanitize')
              return (
              <tr key={log.id} className="border-t border-gray-700/50">
                <td className="p-3 text-xs text-gray-400 whitespace-nowrap">
                  {new Date(log.created_at).toLocaleString()}
                </td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${isSanitize ? 'bg-emerald-900/60 text-emerald-300' : 'bg-gray-700'}`}>{log.event_type}</span>
                </td>
                <td className="p-3 text-gray-300">{isSanitize ? 'local' : (log.provider || '-')}</td>
                <td className="p-3 font-mono text-xs">{isSanitize ? '-' : (log.model_requested || '-')}</td>
                <td className="p-3 text-right text-gray-400">
                  {log.latency_ms ? `${log.latency_ms}ms` : '-'}
                </td>
                <td className="p-3 text-red-400 text-xs truncate max-w-48">
                  {log.error_message || '-'}
                </td>
              </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
