'use client'

import { useState, useEffect, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { Zap, ChevronRight, MessageSquare, Code2, Wand2 } from 'lucide-react'
import clsx from 'clsx'
import Sidebar, { QUICK_PROMPTS } from '@/components/Sidebar'

// Lazy-load Monaco to avoid SSR issues
const ChatPanel = dynamic(() => import('@/components/ChatPanel'), { ssr: false })
const CodeEditor = dynamic(() => import('@/components/CodeEditor'), { ssr: false })

const DEFAULT_CODE = `-- Welcome to Roblox AI Dev Tool
-- Click "Generate" above or ask the AI to write code for you!

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

Players.PlayerAdded:Connect(function(player)
    print("Player joined:", player.Name)
end)
`

type Panel = 'chat' | 'editor'
type Layout = 'chat-only' | 'editor-only' | 'split'

export default function Home() {
  const [backendUrl, setBackendUrl] = useState('http://localhost:8765')
  const [connected, setConnected] = useState(false)
  const [code, setCode] = useState(DEFAULT_CODE)
  const [layout, setLayout] = useState<Layout>('split')
  const [activePanel, setActivePanel] = useState<Panel>('chat')
  const [showQuickPrompts, setShowQuickPrompts] = useState(true)

  // Check backend connectivity
  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(`${backendUrl}/rpc`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'ping', params: {} }),
          signal: AbortSignal.timeout(3000),
        })
        setConnected(res.ok || res.status === 200)
      } catch {
        setConnected(false)
      }
    }
    check()
    const t = setInterval(check, 10000)
    return () => clearInterval(t)
  }, [backendUrl])

  const handleCodeGenerated = useCallback((newCode: string) => {
    setCode(newCode)
    if (layout === 'chat-only') setLayout('split')
    if (layout === 'split') setActivePanel('editor')
  }, [layout])

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary text-text-primary">
      {/* Sidebar */}
      <Sidebar
        activePanel={activePanel}
        onPanelChange={p => { setActivePanel(p); if (layout !== 'split') setLayout(`${p}-only` as Layout) }}
        backendUrl={backendUrl}
        onBackendUrlChange={setBackendUrl}
        connected={connected}
      />

      {/* Main area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Top bar */}
        <header className="flex items-center gap-3 px-4 py-2.5 border-b border-bg-border bg-bg-secondary flex-shrink-0">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-accent-blue" />
            <span className="font-semibold text-sm">Roblox AI Dev Tool</span>
          </div>

          <div className="flex-1" />

          {/* Layout switcher */}
          <div className="flex items-center gap-1 bg-bg-tertiary border border-bg-border rounded-lg p-0.5">
            <LayoutBtn
              icon={<MessageSquare size={13} />}
              label="Chat"
              active={layout === 'chat-only'}
              onClick={() => setLayout('chat-only')}
            />
            <LayoutBtn
              icon={<><MessageSquare size={13} /><ChevronRight size={10} /><Code2 size={13} /></>}
              label="Split"
              active={layout === 'split'}
              onClick={() => setLayout('split')}
            />
            <LayoutBtn
              icon={<Code2 size={13} />}
              label="Editor"
              active={layout === 'editor-only'}
              onClick={() => setLayout('editor-only')}
            />
          </div>

          {/* Status */}
          <div className={clsx(
            'flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border',
            connected
              ? 'text-accent-green border-accent-green/30 bg-accent-green/10'
              : 'text-accent-red border-accent-red/30 bg-accent-red/10'
          )}>
            <span className={clsx('w-1.5 h-1.5 rounded-full', connected ? 'bg-accent-green' : 'bg-accent-red')} />
            {connected ? 'Connected' : 'No backend'}
          </div>
        </header>

        {/* Content */}
        <div className="flex flex-1 min-h-0">
          {/* Chat panel */}
          {(layout === 'chat-only' || layout === 'split') && (
            <div className={clsx(
              'flex flex-col min-h-0 border-r border-bg-border',
              layout === 'split' ? 'w-[420px] flex-shrink-0' : 'flex-1'
            )}>
              {/* Quick prompts */}
              {showQuickPrompts && (
                <div className="px-3 pt-3 pb-0">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-text-muted font-medium flex items-center gap-1">
                      <Wand2 size={11} /> Quick prompts
                    </span>
                    <button onClick={() => setShowQuickPrompts(false)} className="text-xs text-text-muted hover:text-text-primary">
                      ✕
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5 pb-2">
                    {QUICK_PROMPTS.slice(0, 4).map(p => (
                      <button
                        key={p}
                        className="text-xs px-2.5 py-1 rounded-full bg-bg-tertiary border border-bg-border text-text-secondary hover:border-accent-blue hover:text-accent-blue transition-colors truncate max-w-[180px]"
                        title={p}
                        onClick={() => {
                          // Dispatch a custom event to pre-fill the chat input
                          window.dispatchEvent(new CustomEvent('quick-prompt', { detail: p }))
                          setShowQuickPrompts(false)
                        }}
                      >
                        {p.length > 30 ? p.slice(0, 30) + '…' : p}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex-1 min-h-0">
                <ChatPanel backendUrl={backendUrl} onCodeGenerated={handleCodeGenerated} />
              </div>
            </div>
          )}

          {/* Code editor panel */}
          {(layout === 'editor-only' || layout === 'split') && (
            <div className="flex-1 min-w-0 min-h-0">
              <CodeEditor
                code={code}
                onChange={setCode}
                backendUrl={backendUrl}
                fileName="script.luau"
              />
            </div>
          )}
        </div>

        {/* Bottom bar */}
        {!connected && (
          <div className="flex items-center gap-2 px-4 py-2 bg-accent-red/10 border-t border-accent-red/20 text-xs text-accent-red">
            <span className="font-medium">Backend offline.</span>
            <span className="text-accent-red/70">
              Run: <code className="font-mono bg-accent-red/10 px-1 rounded">roblox-dev-tool.exe --web</code> or <code className="font-mono bg-accent-red/10 px-1 rounded">python web_server.py</code>
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

function LayoutBtn({ icon, label, active, onClick }: {
  icon: React.ReactNode
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={clsx(
        'flex items-center gap-0.5 px-2 py-1 rounded-md text-xs transition-all',
        active
          ? 'bg-accent-blue text-white'
          : 'text-text-muted hover:text-text-primary'
      )}
    >
      {icon}
    </button>
  )
}
