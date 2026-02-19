import { useEffect, useState } from 'react'
import { api } from '../../api/client'

interface Props {
  provider: string
  model: string
  onProviderChange: (provider: string) => void
  onModelChange: (model: string) => void
}

interface ModelInfo {
  id: string
  name: string
  provider: string
  context_window: number
  cost_per_1k_input: number
  cost_per_1k_output: number
}

interface ProviderInfo {
  id: string
  name: string
  is_configured: boolean
  model_count: number
}

// Fallback if API fails
const FALLBACK_MODELS: Record<string, string[]> = {
  openai: ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 'o3-mini'],
  anthropic: ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001', 'claude-opus-4-6'],
  ollama: ['llama3.2', 'mistral', 'codellama', 'mixtral'],
}

// Module-level cache so we only fetch once
let cachedProviders: ProviderInfo[] | null = null
let cachedModels: ModelInfo[] | null = null
let fetchPromise: Promise<void> | null = null

export default function ModelSelector({ provider, model, onProviderChange, onModelChange }: Props) {
  const [providers, setProviders] = useState<ProviderInfo[]>(cachedProviders || [])
  const [models, setModels] = useState<ModelInfo[]>(cachedModels || [])
  const [loaded, setLoaded] = useState(!!cachedProviders)

  useEffect(() => {
    if (cachedProviders && cachedModels) {
      setProviders(cachedProviders)
      setModels(cachedModels)
      setLoaded(true)
      return
    }

    if (!fetchPromise) {
      fetchPromise = api.getModels()
        .then((data) => {
          cachedProviders = data.providers
          cachedModels = data.models
        })
        .catch(() => {
          // Use fallback
          cachedProviders = Object.entries(FALLBACK_MODELS).map(([id, ms]) => ({
            id, name: id.charAt(0).toUpperCase() + id.slice(1), is_configured: true, model_count: ms.length,
          }))
          cachedModels = Object.entries(FALLBACK_MODELS).flatMap(([prov, ms]) =>
            ms.map(m => ({ id: m, name: m, provider: prov, context_window: 0, cost_per_1k_input: 0, cost_per_1k_output: 0 }))
          )
        })
    }

    fetchPromise.then(() => {
      setProviders(cachedProviders!)
      setModels(cachedModels!)
      setLoaded(true)
    })
  }, [])

  const providerModels = loaded
    ? models.filter(m => m.provider === provider)
    : (FALLBACK_MODELS[provider] || []).map(id => ({ id, name: id, provider, context_window: 0, cost_per_1k_input: 0, cost_per_1k_output: 0 }))

  const selectedModel = models.find(m => m.id === model && m.provider === provider)

  return (
    <div className="flex items-center gap-2">
      <select
        value={provider}
        onChange={(e) => {
          const newProv = e.target.value
          onProviderChange(newProv)
          const firstModel = models.find(m => m.provider === newProv)
          if (firstModel) onModelChange(firstModel.id)
        }}
        className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-xs outline-none"
      >
        {(providers.length > 0 ? providers : [
          { id: 'openai', name: 'OpenAI', is_configured: true, model_count: 0 },
          { id: 'anthropic', name: 'Anthropic', is_configured: true, model_count: 0 },
          { id: 'ollama', name: 'Ollama', is_configured: true, model_count: 0 },
        ]).map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}{loaded && !p.is_configured ? ' (not configured)' : ''}
          </option>
        ))}
      </select>

      <select
        value={model}
        onChange={(e) => onModelChange(e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-xs outline-none"
      >
        {providerModels.map((m) => (
          <option key={m.id} value={m.id}>{m.name}</option>
        ))}
      </select>

      {selectedModel && selectedModel.cost_per_1k_input > 0 && (
        <span className="text-[10px] text-gray-500" title={`Input: $${selectedModel.cost_per_1k_input}/1K, Output: $${selectedModel.cost_per_1k_output}/1K`}>
          ${selectedModel.cost_per_1k_input}/1K
        </span>
      )}
    </div>
  )
}
