'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Bot, User, Copy, Check, Loader2 } from 'lucide-react'
import clsx from 'clsx'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

interface ChatPanelProps {
  backendUrl: string
  onCodeGenerated?: (code: string) => void
}

function renderContent(text: string) {
  // Simple markdown-ish renderer: code blocks + inline code
  const parts = text.split(/(```[\s\S]*?```)/g)
  return parts.map((part, i) => {
    if (part.startsWith('```')) {
      const lines = part.split('\n')
      const lang = lines[0].replace('```', '').trim() || 'lua'
      const code = lines.slice(1, lines[lines.length - 1] === '```' ? -1 : undefined).join('\n')
      return (
        <pre key={i} className="my-2 rounded-md bg-bg-primary border border-bg-border p-3 overflow-x-auto">
          <code className="text-xs font-mono text-text-primary">{code}</code>
        </pre>
      )
    }
    // Inline code
    const inline = part.split(/(`[^`]+`)/g)
    return (
      <span key={i}>
        {inline.map((s, j) =>
          s.startsWith('`') && s.endsWith('`') ? (
            <code key={j} className="text-xs font-mono bg-bg-border px-1 rounded text-accent-blue">
              {s.slice(1, -1)}
            </code>
          ) : (
            <span key={j}>{s}</span>
          )
        )}
      </span>
    )
  })
}

export default function ChatPanel({ backendUrl, onCodeGenerated }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '0',
      role: 'assistant',
      content: 'Hey! I\'m your Roblox AI assistant. Ask me anything about Luau scripting, game systems, or paste code for a review.',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const copyCode = async (code: string, id: string) => {
    await navigator.clipboard.writeText(code)
    setCopied(id)
    setTimeout(() => setCopied(null), 2000)
  }

  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text }
    const assistantId = (Date.now() + 1).toString()
    const assistantMsg: Message = { id: assistantId, role: 'assistant', content: '', streaming: true }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setLoading(true)

    abortRef.current = new AbortController()

    try {
      const res = await fetch(`${backendUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
        signal: abortRef.current.signal,
      })

      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const reader = res.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) throw new Error('No response body')

      let fullText = ''
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') break
          try {
            const parsed = JSON.parse(data)
            if (parsed.delta) {
              fullText += parsed.delta
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, content: fullText } : m
                )
              )
            }
          } catch {}
        }
      }

      // Check if response contains a code block → offer to open in editor
      const codeMatch = fullText.match(/```(?:lua|luau)?\n([\s\S]*?)```/)
      if (codeMatch && onCodeGenerated) {
        onCodeGenerated(codeMatch[1])
      }

      setMessages(prev =>
        prev.map(m => (m.id === assistantId ? { ...m, streaming: false } : m))
      )
    } catch (err: any) {
      if (err.name === 'AbortError') return
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, content: `⚠ Error: ${err.message}`, streaming: false }
            : m
        )
      )
    } finally {
      setLoading(false)
    }
  }, [input, loading, backendUrl, onCodeGenerated])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map(msg => (
          <div key={msg.id} className={clsx('fade-in flex gap-3', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
            {/* Avatar */}
            <div className={clsx(
              'w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5',
              msg.role === 'user' ? 'bg-accent-blue' : 'bg-bg-tertiary border border-bg-border'
            )}>
              {msg.role === 'user'
                ? <User size={14} className="text-white" />
                : <Bot size={14} className="text-accent-blue" />
              }
            </div>

            {/* Bubble */}
            <div className={clsx(
              'max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed chat-message',
              msg.role === 'user'
                ? 'bg-accent-blue text-white rounded-tr-sm'
                : 'bg-bg-tertiary border border-bg-border text-text-primary rounded-tl-sm'
            )}>
              {msg.content ? (
                <div className={clsx(msg.streaming && 'cursor-blink')}>
                  {renderContent(msg.content)}
                </div>
              ) : (
                <Loader2 size={14} className="animate-spin text-text-muted" />
              )}

              {/* Copy code button */}
              {msg.role === 'assistant' && msg.content.includes('```') && !msg.streaming && (
                <button
                  onClick={() => {
                    const m = msg.content.match(/```(?:lua|luau)?\n([\s\S]*?)```/)
                    if (m) copyCode(m[1], msg.id)
                  }}
                  className="mt-2 flex items-center gap-1 text-xs text-text-muted hover:text-text-primary transition-colors"
                >
                  {copied === msg.id ? <Check size={11} className="text-accent-green" /> : <Copy size={11} />}
                  {copied === msg.id ? 'Copied!' : 'Copy code'}
                </button>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-bg-border p-3">
        <div className="flex gap-2 items-end bg-bg-tertiary border border-bg-border rounded-xl px-3 py-2 focus-within:border-accent-blue transition-colors">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about Roblox scripting… (Enter to send, Shift+Enter for newline)"
            rows={1}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted resize-none outline-none max-h-32 overflow-y-auto"
            style={{ lineHeight: '1.5' }}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || loading}
            className={clsx(
              'w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-all',
              input.trim() && !loading
                ? 'bg-accent-blue hover:bg-accent-blue2 text-white'
                : 'bg-bg-border text-text-muted cursor-not-allowed'
            )}
          >
            {loading
              ? <Loader2 size={13} className="animate-spin" />
              : <Send size={13} />
            }
          </button>
        </div>
        <p className="text-xs text-text-muted mt-1.5 px-1">
          Tip: paste code + ask for a review, or say "generate a shop system"
        </p>
      </div>
    </div>
  )
}
