import { useState, useRef, useCallback } from 'react'
import { Send, Square } from 'lucide-react'

interface Props {
  onSend: (message: string) => void
  isLoading: boolean
  onStop: () => void
}

export default function ChatInput({ onSend, isLoading, onStop }: Props) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || isLoading) return
    onSend(trimmed)
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [input, isLoading, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`
    }
  }

  return (
    <div className="flex items-end gap-2 bg-gray-800 rounded-xl p-2">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        placeholder="Type a message... (sensitive data will be auto-detected)"
        rows={1}
        className="flex-1 bg-transparent resize-none outline-none text-sm px-2 py-1.5 max-h-[200px] placeholder-gray-500"
      />
      {isLoading ? (
        <button
          onClick={onStop}
          className="p-2 rounded-lg bg-red-600 hover:bg-red-700 transition-colors"
          title="Stop generating"
        >
          <Square className="w-4 h-4" />
        </button>
      ) : (
        <button
          onClick={handleSubmit}
          disabled={!input.trim()}
          className="p-2 rounded-lg bg-veil-600 hover:bg-veil-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="Send message"
        >
          <Send className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}
