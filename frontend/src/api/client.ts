const BASE_URL = '/api'

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('veilchat_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Rate limit state — exposed so UI can react
export const rateLimitState = {
  limited: false,
  retryAfter: 0,
  listeners: [] as Array<(limited: boolean, retryAfter: number) => void>,
  notify(limited: boolean, retryAfter: number) {
    this.limited = limited
    this.retryAfter = retryAfter
    this.listeners.forEach(fn => fn(limited, retryAfter))
  },
  subscribe(fn: (limited: boolean, retryAfter: number) => void) {
    this.listeners.push(fn)
    return () => { this.listeners = this.listeners.filter(f => f !== fn) }
  },
}

async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const headers = { ...getAuthHeaders(), ...(init?.headers || {}) }
  const res = await fetch(url, { ...init, headers })
  if (res.status === 401) {
    localStorage.removeItem('veilchat_token')
    localStorage.removeItem('veilchat_user')
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
  }
  if (res.status === 429) {
    const retryAfter = parseInt(res.headers.get('Retry-After') || '60', 10)
    rateLimitState.notify(true, retryAfter)
    setTimeout(() => rateLimitState.notify(false, 0), retryAfter * 1000)
  }
  return res
}

export interface ConversationSummary {
  id: string
  title: string | null
  provider: string
  model: string
  total_messages: number
  created_at: string
}

export interface MessageData {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  sanitized_content?: string
  entities_detected: number
  model_used?: string
  created_at: string
}

export interface EntityData {
  entity_type: string
  original_value: string
  placeholder: string
  confidence: number
  detection_method: string
}

export interface ConversationDetail {
  id: string
  title: string | null
  provider: string
  model: string
  status: string
  total_messages: number
  messages: MessageData[]
  entities: EntityData[]
}

export interface SanitizationEvent {
  original_text: string
  sanitized_text: string
  entities: Array<{
    entity_type: string
    original: string
    placeholder: string
    confidence: number
    start: number
    end: number
    detection_method: string
  }>
}

export interface DashboardStats {
  total_conversations: number
  total_messages: number
  total_entities_detected: number
  total_tokens_used: number
  estimated_cost_usd: number
  active_users: number
  top_entity_types: Array<{ type: string; count: number }>
  requests_today: number
  entities_today: number
}

export interface UsageData {
  period_days: number
  group_by: string
  data: Array<{
    group: string
    request_count: number
    total_tokens: number
    estimated_cost_usd: number
    entities_detected: number
    error_count: number
  }>
}

export interface AuditLogEntry {
  id: string
  event_type: string
  user_id: string | null
  conversation_id: string | null
  provider: string | null
  model_requested: string | null
  http_status: number | null
  latency_ms: number | null
  error_message: string | null
  created_at: string
}

export interface DetectionRule {
  id: string
  name: string
  description: string | null
  entity_type: string
  detection_method: string
  pattern: string | null
  word_list: string[] | null
  priority: number
  confidence: number
  is_active: boolean
  is_built_in: boolean
  created_at: string
}

export interface PolicyData {
  id: string
  name: string
  description: string | null
  entity_type: string
  action: string
  notify: boolean
  severity: string
  min_confidence: number
  is_active: boolean
  is_built_in: boolean
  priority: number
  created_at: string
}

export interface WebhookData {
  id: string
  name: string
  url: string
  secret: string | null
  event_types: string[]
  format: string
  is_active: boolean
  failure_count: number
  last_triggered_at: string | null
  last_error: string | null
  created_at: string
}

export interface ApiKeyData {
  id: string
  name: string
  key_prefix: string
  scopes: string[]
  is_active: boolean
  last_used_at: string | null
  created_at: string
}

export interface ApiKeyCreated {
  id: string
  name: string
  key: string
  key_prefix: string
  scopes: string[]
}

export const api = {
  async listConversations(params?: { q?: string; sort?: string }): Promise<ConversationSummary[]> {
    const searchParams = new URLSearchParams()
    if (params?.q) searchParams.set('q', params.q)
    if (params?.sort) searchParams.set('sort', params.sort)
    const qs = searchParams.toString()
    const res = await authFetch(`${BASE_URL}/conversations${qs ? `?${qs}` : ''}`)
    if (!res.ok) throw new Error('Failed to load conversations')
    return res.json()
  },

  async getConversation(id: string): Promise<ConversationDetail> {
    const res = await authFetch(`${BASE_URL}/conversations/${id}`)
    if (!res.ok) throw new Error('Failed to load conversation')
    return res.json()
  },

  async renameConversation(id: string, title: string): Promise<{ id: string; title: string }> {
    const res = await authFetch(`${BASE_URL}/conversations/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
    if (!res.ok) throw new Error('Failed to rename conversation')
    return res.json()
  },

  async deleteConversation(id: string): Promise<void> {
    const res = await authFetch(`${BASE_URL}/conversations/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error('Failed to delete conversation')
  },

  // --- Admin APIs ---

  async getDashboard(): Promise<DashboardStats> {
    const res = await authFetch(`${BASE_URL}/admin/dashboard`)
    if (!res.ok) throw new Error('Failed to load dashboard')
    return res.json()
  },

  async getUsage(days = 30, groupBy = 'day'): Promise<UsageData> {
    const res = await authFetch(`${BASE_URL}/admin/usage?days=${days}&group_by=${groupBy}`)
    if (!res.ok) throw new Error('Failed to load usage')
    return res.json()
  },

  async getEntityStats(): Promise<{ by_type: Array<{ entity_type: string; count: number }>; total: number }> {
    const res = await authFetch(`${BASE_URL}/admin/entities`)
    if (!res.ok) throw new Error('Failed to load entity stats')
    return res.json()
  },

  async getAuditLogs(limit = 50, offset = 0): Promise<{ total: number; logs: AuditLogEntry[] }> {
    const res = await authFetch(`${BASE_URL}/admin/audit?limit=${limit}&offset=${offset}`)
    if (!res.ok) throw new Error('Failed to load audit logs')
    return res.json()
  },

  async getUsers(): Promise<Array<{ id: string; email: string; display_name: string | null; role: string; is_active: boolean; last_login_at: string | null; created_at: string }>> {
    const res = await authFetch(`${BASE_URL}/admin/users`)
    if (!res.ok) throw new Error('Failed to load users')
    return res.json()
  },

  async updateUser(id: string, data: { role?: string; is_active?: boolean }): Promise<unknown> {
    const res = await authFetch(`${BASE_URL}/admin/users/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to update user')
    }
    return res.json()
  },

  async inviteUser(data: { email: string; role?: string; display_name?: string }): Promise<{ id: string; email: string; role: string; temp_password: string; message: string }> {
    const res = await authFetch(`${BASE_URL}/admin/users/invite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to invite user')
    }
    return res.json()
  },

  async getRules(): Promise<DetectionRule[]> {
    const res = await authFetch(`${BASE_URL}/rules`)
    if (!res.ok) throw new Error('Failed to load rules')
    return res.json()
  },

  async getPolicies(): Promise<PolicyData[]> {
    const res = await authFetch(`${BASE_URL}/policies`)
    if (!res.ok) throw new Error('Failed to load policies')
    return res.json()
  },

  // --- Rules CRUD ---

  async createRule(data: {
    name: string; entity_type: string; detection_method: string;
    description?: string; pattern?: string; word_list?: string[];
    priority?: number; confidence?: number;
  }): Promise<DetectionRule> {
    const res = await authFetch(`${BASE_URL}/rules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to create rule')
    }
    return res.json()
  },

  async updateRule(id: string, data: Record<string, unknown>): Promise<DetectionRule> {
    const res = await authFetch(`${BASE_URL}/rules/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to update rule')
    }
    return res.json()
  },

  async deleteRule(id: string): Promise<void> {
    const res = await authFetch(`${BASE_URL}/rules/${id}`, { method: 'DELETE' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to delete rule')
    }
  },

  // --- Policies CRUD ---

  async createPolicy(data: {
    name: string; entity_type: string; action: string;
    description?: string; severity?: string; notify?: boolean;
    min_confidence?: number; priority?: number;
  }): Promise<PolicyData> {
    const res = await authFetch(`${BASE_URL}/policies`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to create policy')
    }
    return res.json()
  },

  async updatePolicy(id: string, data: Record<string, unknown>): Promise<PolicyData> {
    const res = await authFetch(`${BASE_URL}/policies/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to update policy')
    }
    return res.json()
  },

  async deletePolicy(id: string): Promise<void> {
    const res = await authFetch(`${BASE_URL}/policies/${id}`, { method: 'DELETE' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to delete policy')
    }
  },

  // --- API Keys ---

  async getApiKeys(): Promise<ApiKeyData[]> {
    const res = await authFetch(`${BASE_URL}/api-keys`)
    if (!res.ok) throw new Error('Failed to load API keys')
    return res.json()
  },

  async createApiKey(data: { name: string; scopes?: string[] }): Promise<ApiKeyCreated> {
    const res = await authFetch(`${BASE_URL}/api-keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('Failed to create API key')
    return res.json()
  },

  async revokeApiKey(id: string): Promise<void> {
    const res = await authFetch(`${BASE_URL}/api-keys/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error('Failed to revoke API key')
  },

  // --- Models ---

  async getModels(): Promise<{
    providers: Array<{ id: string; name: string; is_configured: boolean; model_count: number }>
    models: Array<{ id: string; name: string; provider: string; context_window: number; cost_per_1k_input: number; cost_per_1k_output: number }>
  }> {
    const res = await authFetch(`${BASE_URL}/models`)
    if (!res.ok) throw new Error('Failed to load models')
    return res.json()
  },

  // --- Webhooks ---

  async getWebhooks(): Promise<WebhookData[]> {
    const res = await authFetch(`${BASE_URL}/webhooks`)
    if (!res.ok) throw new Error('Failed to load webhooks')
    return res.json()
  },

  async createWebhook(data: { name: string; url: string; event_types?: string[]; format?: string }): Promise<WebhookData> {
    const res = await authFetch(`${BASE_URL}/webhooks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to create webhook')
    }
    return res.json()
  },

  async updateWebhook(id: string, data: { name?: string; url?: string; event_types?: string[]; format?: string; is_active?: boolean }): Promise<WebhookData> {
    const res = await authFetch(`${BASE_URL}/webhooks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to update webhook')
    }
    return res.json()
  },

  async deleteWebhook(id: string): Promise<void> {
    const res = await authFetch(`${BASE_URL}/webhooks/${id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error('Failed to delete webhook')
  },

  async testWebhook(id: string): Promise<{ status: string; message: string }> {
    const res = await authFetch(`${BASE_URL}/webhooks/${id}/test`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Test failed')
    }
    return res.json()
  },

  // --- Licensing ---

  async getLicenseStatus(): Promise<{
    tier: string; tier_name: string; max_users: number; features: string[];
    is_licensed: boolean; expires_at: string | null; days_remaining: number | null;
    license_id: string | null
  }> {
    const res = await authFetch(`${BASE_URL}/licensing/status`)
    if (!res.ok) throw new Error('Failed to load license status')
    return res.json()
  },

  async activateLicense(licenseKey: string): Promise<{
    tier: string; tier_name: string; max_users: number; features: string[];
    is_licensed: boolean; expires_at: string | null; days_remaining: number | null
  }> {
    const res = await authFetch(`${BASE_URL}/licensing/activate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ license_key: licenseKey }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Failed to activate license')
    }
    return res.json()
  },

  async deactivateLicense(): Promise<{ status: string; tier: string }> {
    const res = await authFetch(`${BASE_URL}/licensing/deactivate`, { method: 'DELETE' })
    if (!res.ok) throw new Error('Failed to deactivate license')
    return res.json()
  },

  async getTiers(): Promise<Array<{
    id: string; name: string; level: number; max_users: number;
    max_custom_rules: number; max_webhooks: number;
    audit_retention_days: number; features: string[]
  }>> {
    const res = await authFetch(`${BASE_URL}/licensing/tiers`)
    if (!res.ok) throw new Error('Failed to load tiers')
    return res.json()
  },

  // --- Conversation export ---

  async exportConversation(id: string, format: 'json' | 'csv' = 'json'): Promise<Blob> {
    const res = await authFetch(`${BASE_URL}/conversations/${id}/export?format=${format}`)
    if (!res.ok) throw new Error('Failed to export conversation')
    return res.blob()
  },

  chatStream(params: {
    message: string
    conversation_id?: string
    provider?: string
    model?: string
    temperature?: number
    max_tokens?: number
    system_prompt?: string
  }): {
    eventSource: AbortController
    onSanitization: (cb: (data: SanitizationEvent) => void) => void
    onToken: (cb: (content: string) => void) => void
    onDone: (cb: (data: Record<string, unknown>) => void) => void
    onError: (cb: (error: string) => void) => void
    start: () => Promise<void>
  } {
    const controller = new AbortController()
    let sanitizationCb: ((data: SanitizationEvent) => void) | null = null
    let tokenCb: ((content: string) => void) | null = null
    let doneCb: ((data: Record<string, unknown>) => void) | null = null
    let errorCb: ((error: string) => void) | null = null

    return {
      eventSource: controller,
      onSanitization(cb) { sanitizationCb = cb },
      onToken(cb) { tokenCb = cb },
      onDone(cb) { doneCb = cb },
      onError(cb) { errorCb = cb },
      async start() {
        try {
          const res = await fetch(`${BASE_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
            body: JSON.stringify(params),
            signal: controller.signal,
          })

          if (!res.ok) {
            const text = await res.text()
            errorCb?.(text)
            return
          }

          const reader = res.body?.getReader()
          if (!reader) return

          const decoder = new TextDecoder()
          let buffer = ''

          while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() ?? ''

            let currentEvent = ''
            for (const line of lines) {
              if (line.startsWith('event: ')) {
                currentEvent = line.slice(7)
              } else if (line.startsWith('data: ')) {
                const data = line.slice(6)
                try {
                  const parsed = JSON.parse(data)
                  switch (currentEvent) {
                    case 'sanitization':
                      sanitizationCb?.(parsed)
                      break
                    case 'token':
                      tokenCb?.(parsed.content)
                      break
                    case 'done':
                      doneCb?.(parsed)
                      break
                    case 'error':
                      errorCb?.(parsed.error)
                      break
                  }
                } catch {
                  // Skip malformed JSON
                }
              }
            }
          }
        } catch (err) {
          if ((err as Error).name !== 'AbortError') {
            errorCb?.((err as Error).message)
          }
        }
      },
    }
  },
}
