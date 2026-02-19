import { useState } from 'react'
import { Lock, Eye, Zap, Globe } from 'lucide-react'
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
            <svg width="18" height="22" viewBox="0 0 28 34" fill="none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="hd-s" x1="2" y1="2" x2="26" y2="32" gradientUnits="userSpaceOnUse">
                  <stop offset="0" stopColor="#4A5090"/><stop offset="0.5" stopColor="#5B6BC0"/><stop offset="1" stopColor="#7C8BF5"/>
                </linearGradient>
                <linearGradient id="hd-k" x1="10" y1="10" x2="18" y2="26" gradientUnits="userSpaceOnUse">
                  <stop offset="0" stopColor="#7C8BF5"/><stop offset="1" stopColor="#9AA5FF"/>
                </linearGradient>
              </defs>
              <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" fill="url(#hd-s)" opacity="0.12"/>
              <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" stroke="url(#hd-s)" strokeWidth="1.8" strokeLinejoin="round" fill="none"/>
              <circle cx="14" cy="14" r="3.5" stroke="url(#hd-k)" strokeWidth="1.5" fill="none"/>
              <line x1="14" y1="17.5" x2="14" y2="24" stroke="url(#hd-k)" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
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
              <svg width="56" height="66" viewBox="0 0 28 34" fill="none" xmlns="http://www.w3.org/2000/svg" className="mb-4 opacity-50">
                <defs>
                  <linearGradient id="hp-s" x1="2" y1="2" x2="26" y2="32" gradientUnits="userSpaceOnUse">
                    <stop offset="0" stopColor="#4A5090"/><stop offset="0.5" stopColor="#5B6BC0"/><stop offset="1" stopColor="#7C8BF5"/>
                  </linearGradient>
                  <linearGradient id="hp-k" x1="10" y1="10" x2="18" y2="26" gradientUnits="userSpaceOnUse">
                    <stop offset="0" stopColor="#7C8BF5"/><stop offset="1" stopColor="#9AA5FF"/>
                  </linearGradient>
                </defs>
                <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" fill="url(#hp-s)" opacity="0.12"/>
                <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" stroke="url(#hp-s)" strokeWidth="1.8" strokeLinejoin="round" fill="none"/>
                <circle cx="14" cy="14" r="3.5" stroke="url(#hp-k)" strokeWidth="1.5" fill="none"/>
                <line x1="14" y1="17.5" x2="14" y2="24" stroke="url(#hp-k)" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              <h2 className="text-xl font-display font-semibold tracking-[5px] mb-1">VEIL<span className="font-light text-veil-500">PROXY</span></h2>
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
