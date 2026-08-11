import type { ReactNode } from 'react'
import type { IntentLevel } from '../lib/types'

const INTENT_STYLES: Record<IntentLevel, string> = {
  HOT: 'bg-red-100 text-red-800 border-red-200',
  STRONG: 'bg-orange-100 text-orange-800 border-orange-200',
  GOOD: 'bg-amber-100 text-amber-800 border-amber-200',
  POSSIBLE: 'bg-sky-100 text-sky-800 border-sky-200',
  LOW: 'bg-ink-100 text-ink-600 border-ink-200',
}

export function IntentBadge({ level }: { level: IntentLevel }) {
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-bold
      border tracking-wide ${INTENT_STYLES[level] ?? INTENT_STYLES.LOW}`}>
      {level}
    </span>
  )
}

export function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
  const radius = (size - 6) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100)
  const color =
    score >= 86 ? '#dc2626' : score >= 71 ? '#ea580c'
      : score >= 51 ? '#d97706' : score >= 31 ? '#0284c7' : '#94a3b8'

  return (
    <svg width={size} height={size} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none"
        stroke="#e5e7eb" strokeWidth="5" />
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none"
        stroke={color} strokeWidth="5" strokeLinecap="round"
        strokeDasharray={circumference} strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" textAnchor="middle" dy="0.35em"
        className="fill-ink-900 font-bold" fontSize={size * 0.29}>
        {Math.round(score)}
      </text>
    </svg>
  )
}

export function StatCard({ label, value, hint, accent }: {
  label: string; value: ReactNode; hint?: string; accent?: string
}) {
  return (
    <div className="card p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-ink-500">
        {label}
      </div>
      <div className={`text-2xl font-bold mt-1 ${accent ?? 'text-ink-900'}`}>
        {value}
      </div>
      {hint && <div className="text-xs text-ink-500 mt-1">{hint}</div>}
    </div>
  )
}

export function Chip({ children, tone = 'default' }: {
  children: ReactNode; tone?: 'default' | 'green' | 'red' | 'blue'
}) {
  const tones = {
    default: 'bg-ink-100 text-ink-700 border-ink-200',
    green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    blue: 'bg-sky-50 text-sky-700 border-sky-200',
  }
  return (
    <span className={`inline-flex px-2 py-0.5 rounded border text-xs
      font-medium ${tones[tone]}`}>{children}</span>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-ink-500 text-sm py-12
      justify-center">
      <div className="w-4 h-4 border-2 border-ink-300 border-t-ink-700
        rounded-full animate-spin" />
      {label}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: {
  error: string; onRetry?: () => void
}) {
  return (
    <div className="card p-6 border-red-200 bg-red-50">
      <div className="font-semibold text-red-900 mb-1">Something went wrong</div>
      <div className="text-sm text-red-800 font-mono">{error}</div>
      <div className="text-xs text-red-700 mt-3">
        Check that the API is running: <code>uvicorn app.main:app --reload</code>
      </div>
      {onRetry && (
        <button className="btn-ghost mt-3 border-red-300" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, body, action }: {
  title: string; body: string; action?: ReactNode
}) {
  return (
    <div className="card p-10 text-center">
      <div className="text-lg font-semibold text-ink-800">{title}</div>
      <p className="text-sm text-ink-500 mt-2 max-w-md mx-auto">{body}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

export function humanizeSignal(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  })
}
