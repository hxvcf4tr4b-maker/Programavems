'use client'

import { useState } from 'react'
import { MessageSquare, Code2, Settings, ChevronRight, Zap, BookOpen, Github } from 'lucide-react'
import clsx from 'clsx'

interface SidebarProps {
  activePanel: 'chat' | 'editor'
  onPanelChange: (panel: 'chat' | 'editor') => void
  backendUrl: string
  onBackendUrlChange: (url: string) => void
  connected: boolean
}

const QUICK_PROMPTS = [
  'Generate a DataStore module for saving player data',
  'Create a round-based game loop system',
  'Make a shop UI with proximity prompt',
  'Write a leaderboard using OrderedDataStore',
  'Create a tween-based door script',
  'Generate a weapon system with cooldowns',
]

export default function Sidebar({ activePanel, onPanelChange, backendUrl, onBackendUrlChange, connected }: SidebarProps) {
  const [showSettings, setShowSettings] = useState(false)
  const [urlInput, setUrlInput] = useState(backendUrl)

  return (
    <div className="w-14 flex flex-col items-center py-3 border-r border-bg-border bg-bg-secondary gap-1">
      {/* Logo */}
      <div className="w-9 h-9 rounded-xl bg-accent-blue flex items-center justify-center mb-3 flex-shrink-0">
        <Zap size={18} className="text-white" />
      </div>

      {/* Nav buttons */}
      <NavBtn
        icon={<MessageSquare size={18} />}
        label="Chat"
        active={activePanel === 'chat'}
        onClick={() => onPanelChange('chat')}
      />
      <NavBtn
        icon={<Code2 size={18} />}
        label="Editor"
        active={activePanel === 'editor'}
        onClick={() => onPanelChange('editor')}
      />

      <div className="flex-1" />

      {/* Connection indicator */}
      <div className="relative group">
        <div className={clsx(
          'w-2 h-2 rounded-full mb-2',
          connected ? 'bg-accent-green' : 'bg-accent-red'
        )} />
        <div className="absolute left-10 bottom-0 hidden group-hover:flex items-center bg-bg-tertiary border border-bg-border rounded-md px-2 py-1 text-xs text-text-secondary whitespace-nowrap z-50">
          {connected ? 'Backend connected' : 'Backend offline'}
        </div>
      </div>

      {/* Settings */}
      <NavBtn
        icon={<Settings size={18} />}
        label="Settings"
        active={showSettings}
        onClick={() => setShowSettings(!showSettings)}
      />

      {/* Settings popup */}
      {showSettings && (
        <div className="absolute left-16 bottom-4 z-50 w-72 bg-bg-secondary border border-bg-border rounded-xl shadow-2xl p-4">
          <h3 className="text-sm font-semibold text-text-primary mb-3">Settings</h3>

          <label className="block text-xs text-text-muted mb-1">Backend URL</label>
          <div className="flex gap-2 mb-4">
            <input
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              className="flex-1 bg-bg-primary border border-bg-border rounded-md px-2 py-1.5 text-sm text-text-primary outline-none focus:border-accent-blue"
            />
            <button
              onClick={() => { onBackendUrlChange(urlInput); setShowSettings(false) }}
              className="px-2 py-1.5 bg-accent-blue rounded-md text-xs text-white hover:bg-accent-blue2"
            >
              Save
            </button>
          </div>

          <div className="border-t border-bg-border pt-3">
            <p className="text-xs text-text-muted mb-2">Start backend:</p>
            <pre className="text-xs bg-bg-primary border border-bg-border rounded-md p-2 text-accent-green overflow-x-auto">
              {`set ANTHROPIC_API_KEY=sk-...
roblox-dev-tool.exe --web`}
            </pre>
          </div>

          <div className="border-t border-bg-border pt-3 mt-3 flex items-center gap-2">
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-text-muted hover:text-text-primary transition-colors"
            >
              <Github size={12} /> Source
            </a>
            <span className="text-bg-border">·</span>
            <a
              href="https://create.roblox.com/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-text-muted hover:text-text-primary transition-colors"
            >
              <BookOpen size={12} /> Roblox Docs
            </a>
          </div>
        </div>
      )}
    </div>
  )
}

function NavBtn({ icon, label, active, onClick }: {
  icon: React.ReactNode
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <div className="relative group">
      <button
        onClick={onClick}
        className={clsx(
          'w-9 h-9 rounded-xl flex items-center justify-center transition-all',
          active
            ? 'bg-accent-blue text-white'
            : 'text-text-muted hover:bg-bg-hover hover:text-text-primary'
        )}
      >
        {icon}
      </button>
      <div className="absolute left-11 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-1 bg-bg-tertiary border border-bg-border rounded-md px-2 py-1 text-xs text-text-secondary whitespace-nowrap z-50 pointer-events-none">
        <ChevronRight size={10} />
        {label}
      </div>
    </div>
  )
}

export { QUICK_PROMPTS }
