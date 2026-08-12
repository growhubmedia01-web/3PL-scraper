import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type LeadFilters } from '../lib/api'
import type { Lead, Paginated } from '../lib/types'
import {
  Chip, EmptyState, ErrorBox, IntentBadge, ScoreRing, Spinner,
  formatDate, humanizeSignal,
} from '../components/ui'

const INTENTS = ['HOT', 'STRONG', 'GOOD', 'POSSIBLE', 'LOW']
const BUSINESS_MODELS = [
  { value: 'dtc', label: 'Direct to consumer' },
  { value: 'wholesale', label: 'Wholesale / B2B' },
  { value: 'manufacturer', label: 'Manufacturer' },
  { value: 'retail', label: 'Retail / stockists' },
  { value: 'marketplace', label: 'Marketplace seller' },
  { value: 'subscription', label: 'Subscription' },
  { value: 'importer', label: 'Importer' },
  { value: 'multi_channel', label: 'Multi-channel' },
]
const SORTS = [
  { value: 'score', label: 'Highest score' },
  { value: 'newest', label: 'Newest' },
  { value: 'urgency', label: 'Highest urgency' },
  { value: 'evidence', label: 'Most evidence' },
]

export default function Leads() {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<Paginated<Lead> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const filters: LeadFilters = useMemo(() => ({
    q: params.get('q') || undefined,
    country: params.get('country') || undefined,
    intent: params.get('intent') || undefined,
    urgency: params.get('urgency') || undefined,
    platform: params.get('platform') || undefined,
    business_model: params.get('business_model') || undefined,
    signal: params.get('signal') || undefined,
    min_score: params.get('min_score') ? Number(params.get('min_score')) : undefined,
    has_decision_maker: params.get('has_dm') === '1' ? true : undefined,
    discovered_within_days: params.get('days') ? Number(params.get('days')) : undefined,
    sort: params.get('sort') || 'score',
    page: Number(params.get('page') || 1),
    page_size: 25,
  }), [params])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setError(null)
      setData(await api.leads('3pl', filters))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => { void load() }, [load])

  function update(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value); else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next)
  }

  const activeCount = ['q', 'country', 'intent', 'urgency', 'platform',
    'business_model', 'signal', 'min_score', 'has_dm', 'days']
    .filter((k) => params.get(k)).length

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Leads</h1>
          <p className="text-sm text-ink-500">
            {data ? `${data.total} qualified opportunities` : '—'}
          </p>
        </div>
        <a className="btn-ghost" href={api.exportUrl('3pl', filters)}>
          Export CSV
        </a>
      </div>

      <div className="card p-4">
        <div className="grid md:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="lg:col-span-2">
            <label className="label">Search</label>
            <input className="input" placeholder="Company name or domain"
              defaultValue={params.get('q') || ''}
              onKeyDown={(e) => {
                if (e.key === 'Enter') update('q', e.currentTarget.value)
              }} />
          </div>
          <div>
            <label className="label">Intent</label>
            <select className="input" value={params.get('intent') || ''}
              onChange={(e) => update('intent', e.target.value)}>
              <option value="">All</option>
              {INTENTS.map((i) => <option key={i} value={i}>{i}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Country</label>
            <input className="input" placeholder="GB" maxLength={2}
              defaultValue={params.get('country') || ''}
              onBlur={(e) => update('country', e.target.value.toUpperCase())} />
          </div>
          <div>
            <label className="label">Business model</label>
            <select className="input" value={params.get('business_model') || ''}
              onChange={(e) => update('business_model', e.target.value)}>
              <option value="">All</option>
              {BUSINESS_MODELS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Min score</label>
            <input className="input" type="number" min={0} max={100}
              defaultValue={params.get('min_score') || ''}
              onBlur={(e) => update('min_score', e.target.value)} />
          </div>
          <div>
            <label className="label">Sort</label>
            <select className="input" value={params.get('sort') || 'score'}
              onChange={(e) => update('sort', e.target.value)}>
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center gap-4 mt-3 pt-3 border-t border-ink-100">
          <label className="flex items-center gap-2 text-sm text-ink-600">
            <input type="checkbox" checked={params.get('has_dm') === '1'}
              onChange={(e) => update('has_dm', e.target.checked ? '1' : '')} />
            Has decision maker
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-600">
            <input type="checkbox" checked={params.get('days') === '7'}
              onChange={(e) => update('days', e.target.checked ? '7' : '')} />
            Discovered in last 7 days
          </label>
          {params.get('signal') && (
            <Chip tone="blue">
              signal: {humanizeSignal(params.get('signal')!)}
            </Chip>
          )}
          {activeCount > 0 && (
            <button className="text-sm text-ink-500 underline ml-auto"
              onClick={() => setParams(new URLSearchParams())}>
              Clear {activeCount} filter{activeCount > 1 ? 's' : ''}
            </button>
          )}
        </div>
      </div>

      {error && <ErrorBox error={error} onRetry={load} />}
      {loading && <Spinner />}

      {!loading && data && data.items.length === 0 && (
        <EmptyState
          title="No leads match these filters"
          body={activeCount > 0
            ? 'Try widening your filters, or run discovery to find more companies.'
            : 'Run discovery from the dashboard, or paste a company URL there to test the pipeline on a single brand.'}
          action={<Link className="btn-primary" to="/dashboard">Go to dashboard</Link>}
        />
      )}

      {!loading && data && data.items.length > 0 && (
        <>
          <div className="space-y-2">
            {data.items.map((lead) => <LeadRow key={lead.id} lead={lead} />)}
          </div>
          <Pagination page={data.page} pages={data.pages}
            onChange={(p) => update('page', String(p))} />
        </>
      )}
    </div>
  )
}

function LeadRow({ lead }: { lead: Lead }) {
  return (
    <Link to={`/leads/${lead.id}`}
      className="card p-4 flex gap-4 items-center hover:border-ink-400
        transition-colors">
      <ScoreRing score={lead.score} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold truncate">
            {lead.company_name || lead.domain}
          </span>
          <IntentBadge level={lead.intent_level} />
          {lead.business_model && (
            <Chip tone="blue">{humanizeSignal(lead.business_model)}</Chip>
          )}
          {lead.urgency && <Chip tone="red">{lead.urgency} urgency</Chip>}
        </div>
        <div className="text-sm text-ink-500 mt-0.5">
          {lead.domain}
          {lead.country && ` · ${lead.country}`}
          {lead.platform && ` · ${lead.platform}`}
          {lead.industry && ` · ${lead.industry}`}
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          {lead.signal_types.slice(0, 5).map((signal) => (
            <Chip key={signal}>{humanizeSignal(signal)}</Chip>
          ))}
          {lead.signal_types.length > 5 && (
            <Chip>+{lead.signal_types.length - 5} more</Chip>
          )}
        </div>
      </div>
      <div className="text-right text-sm shrink-0 w-52">
        {lead.has_decision_maker ? (
          <>
            <div className="font-medium truncate">{lead.decision_maker_name}</div>
            <div className="text-ink-500 text-xs truncate">
              {lead.decision_maker_title}
            </div>
            <div className="text-xs text-ink-400 mt-0.5">
              {Math.round((lead.decision_maker_confidence ?? 0) * 100)}% confidence
            </div>
          </>
        ) : (
          <div className="text-ink-400 text-xs">No decision maker yet</div>
        )}
        <div className="text-xs text-ink-400 mt-2">
          {lead.evidence_count} sources · {formatDate(lead.last_analyzed)}
        </div>
      </div>
    </Link>
  )
}

function Pagination({ page, pages, onChange }: {
  page: number; pages: number; onChange: (p: number) => void
}) {
  if (pages <= 1) return null
  return (
    <div className="flex items-center justify-center gap-2 pt-2">
      <button className="btn-ghost" disabled={page <= 1}
        onClick={() => onChange(page - 1)}>Previous</button>
      <span className="text-sm text-ink-500">Page {page} of {pages}</span>
      <button className="btn-ghost" disabled={page >= pages}
        onClick={() => onChange(page + 1)}>Next</button>
    </div>
  )
}
