import { useState, useRef, useCallback } from 'react'
import { Paperclip, Send, Square, X } from 'lucide-react'

const ACCEPTED_TYPES = '.pdf,.docx,.txt,.csv,.xlsx'

interface Props {
  onSend: (message: string, file?: File) => void
  isLoading: boolean
  onStop: () => void
}

export default function ChatInput({ onSend, isLoading, onStop }: Props) {
  const [input, setInput] = useState('')
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim()
    if ((!trimmed && !attachedFile) || isLoading) return
    onSend(trimmed, attachedFile ?? undefined)
    setInput('')
    setAttachedFile(null)
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [input, attachedFile, isLoading, onSend])

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

  const handleFileSelect = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setAttachedFile(file)
    }
    // Reset input so the same file can be re-selected
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const removeFile = () => {
    setAttachedFile(null)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="bg-gray-800 rounded-xl p-2">
      {attachedFile && (
        <div className="flex items-center gap-2 px-2 py-1.5 mb-1.5 bg-gray-700/50 rounded-lg text-xs text-gray-300">
          <Paperclip className="w-3.5 h-3.5 text-veil-400 shrink-0" />
          <span className="truncate">{attachedFile.name}</span>
          <span className="text-gray-500 shrink-0">({formatFileSize(attachedFile.size)})</span>
          <button
            onClick={removeFile}
            className="ml-auto p-0.5 rounded hover:bg-gray-600 transition-colors shrink-0"
            title="Remove file"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
      <div className="flex items-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          onChange={handleFileChange}
          className="hidden"
        />
        <button
          onClick={handleFileSelect}
          disabled={isLoading}
          className="p-2 rounded-lg hover:bg-gray-700 disabled:opacity-40 transition-colors"
          title="Attach file (PDF, DOCX, TXT, CSV, XLSX)"
        >
          <Paperclip className="w-4 h-4 text-gray-400" />
        </button>
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
            disabled={!input.trim() && !attachedFile}
            className="p-2 rounded-lg bg-veil-600 hover:bg-veil-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Send message"
          >
            <Send className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  )
}
