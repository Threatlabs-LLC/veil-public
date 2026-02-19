import { User, Bot, Copy, Check } from 'lucide-react'
import { useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { ChatMessage as ChatMsg } from '../../hooks/useChat'
import clsx from 'clsx'

interface Props {
  message: ChatMsg
}

function CodeBlock({ language, children }: { language: string | undefined; children: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [children])

  return (
    <div className="relative group my-3 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between bg-gray-700 px-3 py-1.5 text-xs text-gray-300">
        <span>{language || 'text'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity hover:text-white"
        >
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || 'text'}
        style={oneDark}
        customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.8rem' }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  )
}

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={clsx('flex gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-veil-600 flex items-center justify-center shrink-0">
          <Bot className="w-4 h-4" />
        </div>
      )}

      <div
        className={clsx(
          'max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
          isUser
            ? 'bg-veil-600 text-white'
            : 'bg-gray-800 text-gray-100'
        )}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap break-words">{message.content}</div>
        ) : (
          <div className="markdown-body break-words">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className || '')
                  const content = String(children).replace(/\n$/, '')

                  if (match) {
                    return <CodeBlock language={match[1]}>{content}</CodeBlock>
                  }

                  return (
                    <code
                      className="bg-gray-700/50 px-1.5 py-0.5 rounded text-[0.85em] font-mono"
                      {...props}
                    >
                      {children}
                    </code>
                  )
                },
                pre({ children }) {
                  return <>{children}</>
                },
                a({ href, children }) {
                  return (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="text-veil-400 hover:underline">
                      {children}
                    </a>
                  )
                },
                table({ children }) {
                  return (
                    <div className="overflow-x-auto my-2">
                      <table className="min-w-full text-xs border border-gray-700">{children}</table>
                    </div>
                  )
                },
                th({ children }) {
                  return <th className="border border-gray-700 px-2 py-1 bg-gray-700/50 text-left font-medium">{children}</th>
                },
                td({ children }) {
                  return <td className="border border-gray-700 px-2 py-1">{children}</td>
                },
                ul({ children }) {
                  return <ul className="list-disc pl-4 my-1 space-y-0.5">{children}</ul>
                },
                ol({ children }) {
                  return <ol className="list-decimal pl-4 my-1 space-y-0.5">{children}</ol>
                },
                blockquote({ children }) {
                  return <blockquote className="border-l-2 border-veil-500 pl-3 my-2 text-gray-400 italic">{children}</blockquote>
                },
                h1({ children }) {
                  return <h1 className="text-lg font-bold mt-3 mb-1">{children}</h1>
                },
                h2({ children }) {
                  return <h2 className="text-base font-bold mt-3 mb-1">{children}</h2>
                },
                h3({ children }) {
                  return <h3 className="text-sm font-bold mt-2 mb-1">{children}</h3>
                },
                p({ children }) {
                  return <p className="my-1.5">{children}</p>
                },
                hr() {
                  return <hr className="my-3 border-gray-700" />
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
            {message.isStreaming && <span className="streaming-cursor" />}
          </div>
        )}

        {/* Entity badges for user messages */}
        {isUser && message.entities && message.entities.length > 0 && (
          <div className="mt-2 pt-2 border-t border-veil-500/30 flex flex-wrap gap-1">
            {message.entities.map((e, i) => (
              <span
                key={i}
                className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-veil-800 text-veil-200"
                title={`${e.original} → ${e.placeholder}`}
              >
                {e.placeholder}
              </span>
            ))}
          </div>
        )}
      </div>

      {isUser && (
        <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center shrink-0">
          <User className="w-4 h-4" />
        </div>
      )}
    </div>
  )
}
