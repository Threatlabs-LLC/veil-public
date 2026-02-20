import { useEffect, useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { MessageSquarePlus, MessageSquare, Settings, SlidersHorizontal, Trash2, Clock, User, Search, Webhook, LogOut, ChevronDown, FileText } from 'lucide-react'
import { api } from '../api/client'

interface ConversationItem {
  id: string
  title: string | null
  model: string
  provider?: string
  total_messages: number
  created_at: string
  updated_at?: string
}

function timeAgo(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = now - then
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(dateStr).toLocaleDateString()
}

type SortOption = 'updated_desc' | 'created_desc' | 'messages_desc'

const SORT_LABELS: Record<SortOption, string> = {
  updated_desc: 'Recent',
  created_desc: 'Newest',
  messages_desc: 'Most messages',
}

export default function Sidebar() {
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [sort, setSort] = useState<SortOption>('updated_desc')
  const [showSort, setShowSort] = useState(false)
  const [tier, setTier] = useState<string>('free')
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    api.getLicenseStatus().then(s => setTier(s.tier)).catch(() => {})
  }, [])

  const loadConversations = async (q?: string) => {
    try {
      const data = await api.listConversations({ q: q || undefined, sort })
      setConversations(data)
    } catch {
      // Silently fail on first load
    }
  }

  useEffect(() => {
    loadConversations(searchQuery || undefined)
  }, [searchQuery, sort, location.pathname])

  // Refresh when tab regains focus (user switches back to the app)
  useEffect(() => {
    const onFocus = () => loadConversations(searchQuery || undefined)
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [searchQuery, sort])

  // Lazy background poll — 30s fallback for long-lived tabs
  useEffect(() => {
    const interval = setInterval(() => loadConversations(searchQuery || undefined), 30_000)
    return () => clearInterval(interval)
  }, [searchQuery, sort])

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.preventDefault()
    e.stopPropagation()
    if (!confirm('Delete this conversation? This cannot be undone.')) return
    try {
      await api.deleteConversation(id)
      setConversations(prev => prev.filter(c => c.id !== id))
      if (location.pathname === `/chat/${id}`) {
        navigate('/')
      }
    } catch {
      // Silently fail
    }
  }

  const activeId = location.pathname.startsWith('/chat/')
    ? location.pathname.split('/chat/')[1]
    : null

  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <Link to="/" className="flex items-center gap-2 mb-4 hover:opacity-80 transition-opacity">
          <svg width="24" height="28" viewBox="0 0 28 34" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="sb-s" x1="2" y1="2" x2="26" y2="32" gradientUnits="userSpaceOnUse">
                <stop offset="0" stopColor="#4A5090"/><stop offset="0.5" stopColor="#5B6BC0"/><stop offset="1" stopColor="#7C8BF5"/>
              </linearGradient>
              <linearGradient id="sb-k" x1="10" y1="10" x2="18" y2="26" gradientUnits="userSpaceOnUse">
                <stop offset="0" stopColor="#7C8BF5"/><stop offset="1" stopColor="#9AA5FF"/>
              </linearGradient>
            </defs>
            <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" fill="url(#sb-s)" opacity="0.12"/>
            <path d="M14 2L2 7V17C2 25 8 30 14 32C20 30 26 25 26 17V7L14 2Z" stroke="url(#sb-s)" strokeWidth="1.8" strokeLinejoin="round" fill="none"/>
            <circle cx="14" cy="14" r="3.5" stroke="url(#sb-k)" strokeWidth="1.5" fill="none"/>
            <line x1="14" y1="17.5" x2="14" y2="24" stroke="url(#sb-k)" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <h1 className="text-base font-display font-semibold tracking-widest">VEIL<span className="font-light text-veil-500">PROXY</span></h1>
          {tier !== 'free' && (
            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
              tier === 'enterprise' ? 'bg-amber-900/50 text-amber-300'
                : tier === 'business' ? 'bg-blue-900/50 text-blue-300'
                : 'bg-veil-900/50 text-veil-300'
            }`}>{tier}</span>
          )}
        </Link>
        <button
          onClick={() => navigate('/')}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-veil-600 hover:bg-veil-700 transition-colors text-sm font-medium"
        >
          <MessageSquarePlus className="w-4 h-4" />
          New Chat
        </button>
      </div>

      {/* Search + Sort */}
      <div className="px-3 pt-2 space-y-1.5">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className="w-full pl-8 pr-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:border-veil-500"
          />
        </div>
        <div className="relative">
          <button
            onClick={() => setShowSort(!showSort)}
            className="flex items-center gap-1 px-2 py-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
          >
            {SORT_LABELS[sort]}
            <ChevronDown className="w-2.5 h-2.5" />
          </button>
          {showSort && (
            <div className="absolute left-0 top-full mt-0.5 bg-gray-800 border border-gray-700 rounded-lg shadow-lg z-10 py-1 min-w-28">
              {(Object.entries(SORT_LABELS) as [SortOption, string][]).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => { setSort(key); setShowSort(false) }}
                  className={`block w-full text-left px-3 py-1.5 text-xs transition-colors ${
                    sort === key ? 'text-veil-400 bg-gray-700/50' : 'text-gray-300 hover:bg-gray-700/50'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Conversation list */}
      <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {conversations.length === 0 && (
          <div className="text-center text-gray-600 text-xs mt-8 px-4">
            {searchQuery ? 'No matching conversations' : 'No conversations yet. Start a new chat!'}
          </div>
        )}
        {conversations.map((conv) => (
          <Link
            key={conv.id}
            to={`/chat/${conv.id}`}
            onMouseEnter={() => setHoveredId(conv.id)}
            onMouseLeave={() => setHoveredId(null)}
            className={`group flex items-center gap-2 px-3 py-2.5 rounded-lg transition-colors text-sm ${
              activeId === conv.id
                ? 'bg-gray-800 text-white'
                : 'text-gray-300 hover:bg-gray-800/60'
            }`}
          >
            <MessageSquare className="w-4 h-4 shrink-0 text-gray-500" />
            <div className="flex-1 min-w-0">
              <div className="truncate">
                {conv.title || 'New conversation'}
              </div>
              <div className="flex items-center gap-2 text-[10px] text-gray-500 mt-0.5">
                <span>{conv.model}</span>
                <span className="opacity-50">·</span>
                <span className="flex items-center gap-0.5">
                  <Clock className="w-2.5 h-2.5" />
                  {timeAgo(conv.updated_at || conv.created_at)}
                </span>
                {conv.total_messages > 0 && (
                  <>
                    <span className="opacity-50">·</span>
                    <span>{conv.total_messages} msg{conv.total_messages !== 1 ? 's' : ''}</span>
                  </>
                )}
              </div>
            </div>
            {hoveredId === conv.id && (
              <div className="flex items-center gap-0.5">
                <button
                  onClick={(e) => handleDelete(e, conv.id)}
                  className="p-1 rounded hover:bg-red-900/50 text-gray-500 hover:text-red-400 transition-colors"
                  title="Delete conversation"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </Link>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-gray-800 space-y-1">
        <Link
          to="/documents"
          className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm ${
            location.pathname === '/documents' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:bg-gray-800'
          }`}
        >
          <FileText className="w-4 h-4" />
          Document Scanner
        </Link>
        <Link
          to="/admin"
          className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm ${
            location.pathname === '/admin' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:bg-gray-800'
          }`}
        >
          <Settings className="w-4 h-4" />
          Admin Dashboard
        </Link>
        <Link
          to="/webhooks"
          className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm ${
            location.pathname === '/webhooks' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:bg-gray-800'
          }`}
        >
          <Webhook className="w-4 h-4" />
          Webhooks
        </Link>
        <Link
          to="/settings"
          className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm ${
            location.pathname === '/settings' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:bg-gray-800'
          }`}
        >
          <SlidersHorizontal className="w-4 h-4" />
          Settings
        </Link>
        <Link
          to="/profile"
          className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm ${
            location.pathname === '/profile' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:bg-gray-800'
          }`}
        >
          <User className="w-4 h-4" />
          Profile
        </Link>
        <button
          onClick={() => {
            localStorage.removeItem('veilchat_token')
            localStorage.removeItem('veilchat_user')
            navigate('/login')
          }}
          className="flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm text-gray-400 hover:bg-red-900/30 hover:text-red-400 w-full"
        >
          <LogOut className="w-4 h-4" />
          Sign Out
        </button>
        <div className="text-xs text-gray-600 px-3 pt-1 font-mono">VeilProxy v0.2.0</div>
      </div>
    </aside>
  )
}
