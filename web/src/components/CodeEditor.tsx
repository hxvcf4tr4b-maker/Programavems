'use client'

import { useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import { Play, Download, Copy, Check, Loader2, Wand2, RefreshCw } from 'lucide-react'
import clsx from 'clsx'

interface CodeEditorProps {
  code: string
  onChange: (code: string) => void
  backendUrl: string
  fileName?: string
}

export default function CodeEditor({ code, onChange, backendUrl, fileName = 'script.luau' }: CodeEditorProps) {
  const [reviewing, setReviewing] = useState(false)
  const [review, setReview] = useState('')
  const [copied, setCopied] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generatePrompt, setGeneratePrompt] = useState('')
  const [showGenerate, setShowGenerate] = useState(false)
  const editorRef = useRef<any>(null)

  const handleEditorMount = (editor: any) => {
    editorRef.current = editor
  }

  const copyCode = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const downloadCode = () => {
    const blob = new Blob([code], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    a.click()
    URL.revokeObjectURL(url)
  }

  const reviewCode = async () => {
    if (!code.trim()) return
    setReviewing(true)
    setReview('')
    try {
      const res = await fetch(`${backendUrl}/api/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, fileName }),
      })
      const data = await res.json()
      setReview(data.review || data.error || 'No response')
    } catch (err: any) {
      setReview(`Error: ${err.message}`)
    } finally {
      setReviewing(false)
    }
  }

  const generateCode = async () => {
    if (!generatePrompt.trim()) return
    setGenerating(true)
    try {
      const res = await fetch(`${backendUrl}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feature: generatePrompt, scriptType: 'Script' }),
      })
      const data = await res.json()
      if (data.code) {
        onChange(data.code)
        setShowGenerate(false)
        setGeneratePrompt('')
        setReview('')
      }
    } catch (err: any) {
      setReview(`Error: ${err.message}`)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-bg-border bg-bg-secondary">
        <span className="text-xs text-text-muted font-mono flex-1">{fileName}</span>

        {/* Generate button */}
        <button
          onClick={() => setShowGenerate(!showGenerate)}
          className={clsx(
            'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
            showGenerate
              ? 'bg-accent-blue text-white'
              : 'bg-bg-hover text-text-secondary hover:text-text-primary'
          )}
        >
          <Wand2 size={12} />
          Generate
        </button>

        {/* Review button */}
        <button
          onClick={reviewCode}
          disabled={reviewing || !code.trim()}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-bg-hover text-text-secondary hover:text-text-primary disabled:opacity-50 transition-colors"
        >
          {reviewing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Review
        </button>

        {/* Copy */}
        <button
          onClick={copyCode}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-bg-hover text-text-secondary hover:text-text-primary transition-colors"
        >
          {copied ? <Check size={12} className="text-accent-green" /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>

        {/* Download */}
        <button
          onClick={downloadCode}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-bg-hover text-text-secondary hover:text-text-primary transition-colors"
        >
          <Download size={12} />
          Save
        </button>
      </div>

      {/* Generate prompt bar */}
      {showGenerate && (
        <div className="flex gap-2 px-3 py-2 border-b border-bg-border bg-bg-tertiary">
          <input
            value={generatePrompt}
            onChange={e => setGeneratePrompt(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && generateCode()}
            placeholder="Describe what to generate… e.g. 'a shop system with DataStore'"
            className="flex-1 bg-bg-primary border border-bg-border rounded-md px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent-blue transition-colors"
            autoFocus
          />
          <button
            onClick={generateCode}
            disabled={generating || !generatePrompt.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-accent-blue hover:bg-accent-blue2 text-white disabled:opacity-50 transition-colors"
          >
            {generating ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
            {generating ? 'Generating…' : 'Generate'}
          </button>
        </div>
      )}

      {/* Monaco editor */}
      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          language="lua"
          value={code}
          onChange={v => onChange(v || '')}
          onMount={handleEditorMount}
          theme="vs-dark"
          options={{
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'Fira Code', Consolas, monospace",
            fontLigatures: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            lineNumbers: 'on',
            renderLineHighlight: 'line',
            bracketPairColorization: { enabled: true },
            padding: { top: 12, bottom: 12 },
            smoothScrolling: true,
            cursorBlinking: 'smooth',
            tabSize: 2,
          }}
        />
      </div>

      {/* Review output */}
      {review && (
        <div className="border-t border-bg-border bg-bg-secondary">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-bg-border">
            <span className="text-xs font-medium text-text-secondary">AI Review</span>
            <button onClick={() => setReview('')} className="text-xs text-text-muted hover:text-text-primary">
              ✕ Close
            </button>
          </div>
          <div className="p-3 max-h-48 overflow-y-auto text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
            {review}
          </div>
        </div>
      )}
    </div>
  )
}
