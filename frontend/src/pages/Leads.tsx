import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { SERVICE, api, type LeadFilters } from '../lib/api'
import type { Lead, Paginated } from '../lib/types'
import { DEFAULT_LABELS, useTaxonomy } from '../lib/useTaxonomy'
import {
  Chip, EmptyState, ErrorBox, IntentBadge, ScoreRing, Spinner,
  formatDate, humanizeSignal,
} from '../components/ui'

const INTENTS = ['HOT', 'STRONG', 'GOOD', 'POSSIBLE', 'LOW']
const FRESHNESS = [
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 180 days' },
  { value: '365', label: 'Last 12 months' },
]
const US_STATES = ('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD '
  + 'MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT '
  + 'VA WA WV WI WY').split(' ')
const FILTER_KEYS = ['q', 'country', 'intent', 'urgency', 'platform',
  'business_model', 'signal', 'min_score', 'has_dm', 'days', 'state',
  'employee_band', 'company_type', 'product_category', 'interest_type',
  'vehicle_segment', 'signal_within_days']
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
  const taxonomy = useTaxonomy()
  const labels = taxonomy?.ui_labels ?? DEFAULT_LABELS

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
    state: params.get('state') || undefined,
    employee_band: params.get('employee_band') || undefined,
    company_type: params.get('company_type') || undefined,
    product_category: params.get('product_category') || undefined,
    interest_type: params.get('interest_type') || undefined,
    vehicle_segment: params.get('vehicle_segment') || undefined,
    signal_within_days: params.get('signal_within_days')
      ? Number(params.get('signal_within_days')) : undefined,
    sort: params.get('sort') || 'score',
    page: Number(params.get('page') || 1),
    page_size: 25,
  }), [params])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setError(null)
      setData(await api.leads(SERVICE, filters))
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

  const activeCount = FILTER_KEYS.filter((k) => params.get(k)).length
  const select = (key: string, label: string,
    options: { value: string; label: string }[]) => (
    <div>
      <label className="label">{label}</label>
      <select className="input" value={params.get(key) || ''}
        onChange={(e) => update(key, e.target.value)}>
        <option value="">All</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
  const opts = (values: string[] | undefined) =>
    (values || []).map((v) => ({ value: v, label: humanizeSignal(v) }))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Leads</h1>
          <p className="text-sm text-ink-500">
            {data ? `${data.total} qualified opportunities` : '—'}
          </p>
        </div>
        <a className="btn-ghost" href={api.exportUrl(SERVICE, filters)}>
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
          {select('state', 'HQ state', US_STATES.map((s) => ({ value: s, label: s })))}
          {select('employee_band', 'Size band', opts(taxonomy?.employee_bands))}
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
          {select('company_type', 'Company type', opts(taxonomy?.company_types))}
          {select('product_category', 'Product category',
            opts(taxonomy ? Object.keys(taxonomy.product_taxonomy) : []))}
          {select('vehicle_segment', labels.segment, opts(taxonomy?.vehicle_segments))}
          {select('signal', 'Signal type', (taxonomy?.signals || [])
            .filter((s) => s.dimension !== 'negative')
            .map((s) => ({ value: s.signal_type, label: s.signal_name })))}
          {select('interest_type', 'Product interest',
            Object.entries(labels.interest_types)
              .map(([value, label]) => ({ value, label })))}
          {select('signal_within_days', 'Signal freshness', FRESHNESS)}
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
          {lead.company_type && (
            <Chip tone="blue">{humanizeSignal(lead.company_type)}</Chip>
          )}
          {lead.employee_band && <Chip>{humanizeSignal(lead.employee_band)}</Chip>}
          {lead.urgency && <Chip tone="red">{lead.urgency} urgency</Chip>}
          {lead.location_unverified && <Chip>location unverified</Chip>}
        </div>
        <div className="text-sm text-ink-500 mt-0.5">
          {lead.domain}
          {lead.headquarters
            ? ` · ${lead.headquarters}`
            : lead.headquarters_state ? ` · ${lead.headquarters_state}`
              : lead.country && ` · ${lead.country}`}
          {lead.latest_signal_type && ` · latest: ${humanizeSignal(lead.latest_signal_type)}`
            + (lead.latest_signal_at ? ` (${formatDate(lead.latest_signal_at)})` : '')}
        </div>
        {lead.product_demand_summary && (
          <div className="text-sm text-ink-700 mt-1 line-clamp-2">
            {lead.product_demand_summary}
          </div>
        )}
        {lead.product_categories && lead.product_categories.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {lead.product_categories.slice(0, 4).map((c) => (
              <Chip key={c} tone="green">{c}</Chip>
            ))}
          </div>
        )}
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
          {lead.confidence != null && ` · ${Math.round(lead.confidence * 100)}% conf.`}
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
