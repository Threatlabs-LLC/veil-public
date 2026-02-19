import { useEffect, useState, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { Pencil, Check, Download } from 'lucide-react'
import { api } from '../api/client'
import { useChat, ChatMessage as ChatMsg } from '../hooks/useChat'
import ChatInput from '../components/chat/ChatInput'
import ChatMessage from '../components/chat/ChatMessage'
import SanitizationPanel from '../components/sanitization/SanitizationPanel'
import ModelSelector from '../components/chat/ModelSelector'

export default function Chat() {
  const { id } = useParams<{ id: string }>()
  const [loading, setLoading] = useState(true)
  const [provider, setProvider] = useState('openai')
  const [model, setModel] = useState('gpt-4o-mini')
  const [title, setTitle] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const titleInputRef = useRef<HTMLInputElement>(null)

  const chat = useChat({
    conversationId: id,
    provider,
    model,
  })

  useEffect(() => {
    if (!id) return

    const loadConversation = async () => {
      try {
        const data = await api.getConversation(id)
        setProvider(data.provider)
        setModel(data.model)
        setTitle(data.title)

        const loaded: ChatMsg[] = data.messages.map((m) => ({
          id: m.id,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          sanitizedContent: m.sanitized_content ?? undefined,
        }))
        chat.setMessages(loaded)
      } catch {
        // Conversation may not exist yet
      } finally {
        setLoading(false)
      }
    }

    loadConversation()
  }, [id])

  const handleRename = async () => {
    if (!id || !titleDraft.trim()) {
      setEditingTitle(false)
      return
    }
    try {
      const result = await api.renameConversation(id, titleDraft.trim())
      setTitle(result.title)
    } catch {
      // silently fail
    }
    setEditingTitle(false)
  }

  const startEditing = () => {
    setTitleDraft(title || '')
    setEditingTitle(true)
    setTimeout(() => titleInputRef.current?.focus(), 50)
  }

  const handleExport = async (format: 'json' | 'csv') => {
    if (!id) return
    try {
      const blob = await api.exportConversation(id, format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `conversation-${id.slice(0, 8)}.${format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // silently fail
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        Loading...
      </div>
    )
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex-1 flex flex-col">
        <header className="h-14 border-b border-gray-800 flex items-center justify-between px-4">
          <div className="flex items-center gap-2 min-w-0">
            <svg width="18" height="22" viewBox="0 0 28 34" fill="none" xmlns="http://www.w3.org/2000/svg" className="shrink-0">
              <defs>
                <linearGradient id="ch-s" x1="2" y1="2" x2="26" y2="32" gradientUnits="userSpaceOnUse">
                  <stop offset="0" stopColor="#4A5090"/><stop offset="0.5" stopColor="#5B6BC0"/><stop offset="1" stopColor="#7C8BF5"/>
                </linearGradient>
                <linearGradient id="ch-k" x1="10" y1="10" x2="18" y2="26" gradientUnits="userSpaceOnUse">
                  <stop offset="0" stopColor="#7C8BF5"/><stop offset="1" stopColor="#9AA5FF"/>
                </linearGradient>
              </defs>
              <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" fill="url(#ch-s)" opacity="0.12"/>
              <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" stroke="url(#ch-s)" strokeWidth="1.8" strokeLinejoin="round" fill="none"/>
              <circle cx="14" cy="14" r="3.5" stroke="url(#ch-k)" strokeWidth="1.5" fill="none"/>
              <line x1="14" y1="17.5" x2="14" y2="24" stroke="url(#ch-k)" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            {editingTitle ? (
              <form onSubmit={(e) => { e.preventDefault(); handleRename() }} className="flex items-center gap-1">
                <input
                  ref={titleInputRef}
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  onBlur={handleRename}
                  className="bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-sm font-medium focus:outline-none focus:border-veil-500"
                  onKeyDown={(e) => { if (e.key === 'Escape') setEditingTitle(false) }}
                />
                <button type="submit" className="p-1 text-veil-400 hover:text-veil-300">
                  <Check className="w-3.5 h-3.5" />
                </button>
              </form>
            ) : (
              <button onClick={startEditing} className="flex items-center gap-1.5 group min-w-0">
                <span className="font-medium truncate">{title || 'Untitled Chat'}</span>
                <Pencil className="w-3 h-3 text-gray-600 group-hover:text-gray-400 shrink-0" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="relative group">
              <button className="p-1.5 text-gray-400 hover:text-white rounded hover:bg-gray-800 transition-colors">
                <Download className="w-4 h-4" />
              </button>
              <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                <button onClick={() => handleExport('json')} className="block w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-t-lg">
                  Export JSON
                </button>
                <button onClick={() => handleExport('csv')} className="block w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 rounded-b-lg">
                  Export CSV
                </button>
              </div>
            </div>
            <ModelSelector
              provider={provider}
              model={model}
              onProviderChange={setProvider}
              onModelChange={setModel}
            />
          </div>
        </header>

        <div className="flex-1 overflow-y-auto chat-scroll">
          <div className="max-w-3xl mx-auto py-4 px-4 space-y-4">
            {chat.messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
          </div>
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
