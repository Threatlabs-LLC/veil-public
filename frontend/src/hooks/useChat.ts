import { useState, useCallback, useRef } from 'react'
import { api, SanitizationEvent } from '../api/client'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sanitizedContent?: string
  entities?: SanitizationEvent['entities']
  isStreaming?: boolean
}

interface UseChatOptions {
  conversationId?: string
  provider?: string
  model?: string
  onConversationCreated?: (id: string) => void
}

export function useChat(options: UseChatOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [currentSanitization, setCurrentSanitization] = useState<SanitizationEvent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const conversationIdRef = useRef(options.conversationId)

  const sendMessage = useCallback(async (content: string) => {
    setIsLoading(true)
    setError(null)

    // Add user message
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
    }
    setMessages(prev => [...prev, userMsg])

    // Add placeholder assistant message
    const assistantId = `assistant-${Date.now()}`
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      isStreaming: true,
    }
    setMessages(prev => [...prev, assistantMsg])

    const stream = api.chatStream({
      message: content,
      conversation_id: conversationIdRef.current,
      provider: options.provider ?? 'openai',
      model: options.model ?? 'gpt-4o-mini',
    })

    abortRef.current = stream.eventSource

    stream.onSanitization((data) => {
      setCurrentSanitization(data)
      // Update user message with sanitization info
      setMessages(prev =>
        prev.map(m =>
          m.id === userMsg.id
            ? { ...m, sanitizedContent: data.sanitized_text, entities: data.entities }
            : m
        )
      )
    })

    stream.onToken((token) => {
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, content: m.content + token }
            : m
        )
      )
    })

    stream.onDone((data) => {
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, isStreaming: false }
            : m
        )
      )
      setIsLoading(false)

      // Track conversation ID for follow-up messages
      if (data.conversation_id && !conversationIdRef.current) {
        conversationIdRef.current = data.conversation_id as string
        options.onConversationCreated?.(data.conversation_id as string)
      }
    })

    stream.onError((err) => {
      setError(err)
      setIsLoading(false)
      // Remove the empty assistant message on error
      setMessages(prev => prev.filter(m => m.id !== assistantId))
    })

    await stream.start()
  }, [options])

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
    setIsLoading(false)
    setMessages(prev =>
      prev.map(m => m.isStreaming ? { ...m, isStreaming: false } : m)
    )
  }, [])

  return {
    messages,
    setMessages,
    isLoading,
    currentSanitization,
    error,
    sendMessage,
    stopStreaming,
    conversationId: conversationIdRef.current,
  }
}
