import { useState } from 'react'
import { Shield, Lock, Eye, Zap, Globe } from 'lucide-react'
import { useChat } from '../hooks/useChat'
import ChatInput from '../components/chat/ChatInput'
import ChatMessage from '../components/chat/ChatMessage'
import SanitizationPanel from '../components/sanitization/SanitizationPanel'
import ModelSelector from '../components/chat/ModelSelector'

const FEATURES = [
  {
    icon: Eye,
    title: 'PII Detection',
    description: 'Automatically detects names, emails, phone numbers, SSNs, and more using NER + regex + word lists.',
  },
  {
    icon: Lock,
    title: 'Real-time Sanitization',
    description: 'Sensitive data is replaced with consistent placeholders before reaching any LLM provider.',
  },
  {
    icon: Zap,
    title: 'Transparent Rehydration',
    description: 'Responses are rehydrated with original values so you see natural language — the LLM never does.',
  },
  {
    icon: Globe,
    title: 'Multi-Provider Gateway',
    description: 'Works with OpenAI, Anthropic, and any OpenAI-compatible API including local Ollama models.',
  },
]

export default function Home() {
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState('gpt-4o-mini')

  const chat = useChat({
    provider,
    model,
    onConversationCreated: (id) => {
      window.history.replaceState(null, '', `/chat/${id}`)
    },
  })

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex-1 flex flex-col">
        <header className="h-14 border-b border-gray-800 flex items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-veil-500" />
            <span className="font-medium">New Chat</span>
          </div>
          <ModelSelector
            provider={provider}
            model={model}
            onProviderChange={setProvider}
            onModelChange={setModel}
          />
        </header>

        <div className="flex-1 overflow-y-auto chat-scroll">
          {chat.messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full px-4">
              <Shield className="w-14 h-14 mb-3 text-veil-600 opacity-50" />
              <h2 className="text-2xl font-bold mb-1">Veil</h2>
              <p className="text-sm text-gray-400 mb-8 max-w-md text-center">
                Enterprise LLM sanitization proxy — your messages are scanned and scrubbed before reaching any AI provider.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl w-full mb-8">
                {FEATURES.map((f) => (
                  <div key={f.title} className="p-4 bg-gray-800/40 border border-gray-800 rounded-xl">
                    <div className="flex items-center gap-2 mb-2">
                      <f.icon className="w-4 h-4 text-veil-400" />
                      <h3 className="font-medium text-sm">{f.title}</h3>
                    </div>
                    <p className="text-xs text-gray-400 leading-relaxed">{f.description}</p>
                  </div>
                ))}
              </div>

              <p className="text-xs text-gray-600">
                Type a message below to start a protected conversation.
              </p>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto py-4 px-4 space-y-4">
              {chat.messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-gray-800 p-4">
          <div className="max-w-3xl mx-auto">
            <ChatInput
              onSend={chat.sendMessage}
              isLoading={chat.isLoading}
              onStop={chat.stopStreaming}
            />
            {chat.error && (
              <p className="text-red-400 text-sm mt-2">{chat.error}</p>
            )}
          </div>
        </div>
      </div>

      <SanitizationPanel sanitization={chat.currentSanitization} />
    </div>
  )
}
