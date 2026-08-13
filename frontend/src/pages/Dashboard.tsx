import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { DashboardStats, Health } from '../lib/types'
import {
  Chip, ErrorBox, Spinner, StatCard, humanizeSignal,
} from '../components/ui'

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [seedUrl, setSeedUrl] = useState('')

  const [wakingUp, setWakingUp] = useState(false)

  const load = useCallback(async () => {
    try {
      setError(null)
      // Show "waking up" message after 2s if still loading (Render cold start)
      const wakeTimer = setTimeout(() => setWakingUp(true), 2000)
      const [s, h] = await Promise.all([api.stats(), api.health()])
      clearTimeout(wakeTimer)
      setWakingUp(false)
      setStats(s); setHealth(h)
    } catch (err) {
      setWakingUp(false)
      setError((err as Error).message)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  async function act(name: string, fn: () => Promise<{ message: string }>) {
    setBusy(name); setNotice(null)
    try {
      const res = await fn()
      setNotice(res.message)
      setTimeout(() => void load(), 2500)
    } catch (err) {
      setNotice(`Failed: ${(err as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  if (error) return <ErrorBox error={error} onRetry={load} />
  if (!stats || !health) return (
    <div className="flex flex-col items-center justify-center min-h-[300px] gap-4 text-center">
      <Spinner />
      {wakingUp && (
        <div className="text-sm text-gray-500 animate-pulse max-w-xs">
          ⏳ Server is waking up… this takes up to 30 seconds on the free tier.
          <br />Retrying automatically, please wait.
        </div>
      )}
    </div>
  )

  const setupIssues = [
    !health.database.url_configured &&
      'Set your Supabase database password in backend/.env (DATABASE_URL).',
    !health.search.ok &&
      'No search provider configured — discovery will find nothing.',
    !health.llm.ok &&
      'No LLM key configured — scoring runs on deterministic signals only.',
  ].filter(Boolean) as string[]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Dashboard</h1>
        <div className="flex gap-2">
          <button className="btn-ghost" disabled={busy !== null}
            onClick={() => act('discovery', () => api.runDiscovery('3pl', 50))}>
            {busy === 'discovery' ? 'Starting…' : 'Run discovery'}
          </button>
          <button className="btn-ghost" disabled={busy !== null}
            onClick={() => act('queue', () => api.processQueue(25))}>
            {busy === 'queue' ? 'Starting…' : 'Process queue'}
          </button>
          <button className="btn-primary" disabled={busy !== null}
            onClick={() => act('autopilot', async () => {
              await api.runDiscovery('3pl', 50)
              const res = await api.processQueue(25)
              return { message: "Auto pilot triggered: " + res.message }
            })}>
            {busy === 'autopilot' ? 'Running Auto Pilot…' : 'Auto Pilot ✨'}
          </button>
        </div>
      </div>

      {notice && (
        <div className="card p-3 text-sm bg-sky-50 border-sky-200 text-sky-900">
          {notice}
        </div>
      )}

      {setupIssues.length > 0 && (
        <div className="card p-4 border-amber-200 bg-amber-50">
          <div className="font-semibold text-amber-900 text-sm mb-2">
            Setup incomplete
          </div>
          <ul className="text-sm text-amber-800 space-y-1 list-disc pl-5">
            {setupIssues.map((issue) => <li key={issue}>{issue}</li>)}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard label="Companies" value={stats.total_companies} />
        <StatCard label="Opportunities" value={stats.total_opportunities} />
        <StatCard label="Hot" value={stats.hot_leads} accent="text-red-600" />
        <StatCard label="Strong" value={stats.strong_leads}
          accent="text-orange-600" />
        <StatCard label="New (7d)" value={stats.new_leads_7d} />
        <StatCard label="Countries" value={stats.countries} />
        <StatCard label="Avg score" value={stats.average_score.toFixed(1)} />
      </div>

      <div className="grid lg:grid-cols-2 xl:grid-cols-4 gap-4">
        <div className="card p-4">
          <h2 className="font-semibold text-sm mb-3">Pipeline health</h2>
          <dl className="text-sm space-y-2">
            <Row label="Crawled" value={`${stats.companies_crawled}`} />
            <Row label="Crawl success rate"
              value={`${stats.crawl_success_rate}%`} />
            <Row label="Rejected" value={`${stats.companies_rejected}`} />
            <Row label="Signals detected" value={`${stats.signals_detected}`} />
            <Row label="Decision makers"
              value={`${stats.decision_makers_identified}`} />
            <Row label="AI calls"
              value={`${stats.ai_calls} (${stats.ai_failures} failed)`} />
            <Row label="Estimated API cost"
              value={`$${stats.estimated_cost_usd.toFixed(4)}`} />
          </dl>
        </div>

        <div className="card p-4">
          <h2 className="font-semibold text-sm mb-3">Intent distribution</h2>
          {stats.by_intent.length === 0
            ? <p className="text-sm text-ink-400">No opportunities scored yet.</p>
            : (
              <div className="space-y-2">
                {stats.by_intent.map((row) => (
                  <BarRow key={row.intent_level} label={row.intent_level}
                    count={row.count}
                    max={Math.max(...stats.by_intent.map((r) => r.count))} />
                ))}
              </div>
            )}
        </div>

        <div className="card p-4">
          <h2 className="font-semibold text-sm mb-3">Business models</h2>
          {!stats.by_business_model || stats.by_business_model.length === 0
            ? <p className="text-sm text-ink-400">Nothing classified yet.</p>
            : (
              <div className="flex flex-wrap gap-1.5">
                {stats.by_business_model.map((row) => (
                  <Link key={row.business_model}
                    to={`/leads?business_model=${row.business_model}`}>
                    <Chip tone="blue">
                      {humanizeSignal(row.business_model)} · {row.count}
                    </Chip>
                  </Link>
                ))}
              </div>
            )}
        </div>

        <div className="card p-4">
          <h2 className="font-semibold text-sm mb-3">Top signals</h2>
          {stats.by_signal.length === 0
            ? <p className="text-sm text-ink-400">No signals detected yet.</p>
            : (
              <div className="flex flex-wrap gap-1.5">
                {stats.by_signal.slice(0, 12).map((row) => (
                  <Link key={row.signal_type}
                    to={`/leads?signal=${row.signal_type}`}>
                    <Chip>{humanizeSignal(row.signal_type)} · {row.count}</Chip>
                  </Link>
                ))}
              </div>
            )}
        </div>
      </div>

      <div className="card p-4">
        <h2 className="font-semibold text-sm mb-1">Test the pipeline</h2>
        <p className="text-xs text-ink-500 mb-3">
          Paste any brand's website to run the full pipeline against one company
          — crawl, classify, detect signals, score, find decision makers.
        </p>
        <form className="flex gap-2" onSubmit={async (e) => {
          e.preventDefault()
          if (!seedUrl.trim()) return
          setBusy('add'); setNotice(null)
          try {
            const res = await api.addCompany(seedUrl.trim())
            setNotice(`${res.message} — processing in the background.`)
            setSeedUrl('')
            setTimeout(() => void load(), 4000)
          } catch (err) {
            setNotice(`Failed: ${(err as Error).message}`)
          } finally { setBusy(null) }
        }}>
          <input className="input flex-1" placeholder="https://examplebrand.com"
            value={seedUrl} onChange={(e) => setSeedUrl(e.target.value)} />
          <button className="btn-primary" disabled={busy !== null}>
            {busy === 'add' ? 'Adding…' : 'Analyze company'}
          </button>
        </form>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-ink-500">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  )
}

function BarRow({ label, count, max }: {
  label: string; count: number; max: number
}) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="font-medium">{label}</span>
        <span className="text-ink-500 tabular-nums">{count}</span>
      </div>
      <div className="h-2 bg-ink-100 rounded-full overflow-hidden">
        <div className="h-full bg-ink-700 rounded-full"
          style={{ width: `${max ? (count / max) * 100 : 0}%` }} />
      </div>
    </div>
  )
}
