import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          primary:   '#0f0f10',
          secondary: '#18181b',
          tertiary:  '#1e1e22',
          hover:     '#26262c',
          border:    '#2e2e36',
        },
        accent: {
          blue:      '#3b82f6',
          blue2:     '#2563eb',
          green:     '#22c55e',
          yellow:    '#eab308',
          red:       '#ef4444',
        },
        text: {
          primary:   '#f4f4f5',
          secondary: '#a1a1aa',
          muted:     '#71717a',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
export default config
