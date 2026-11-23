import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { SERVICE, api } from '../lib/api'
import type {
  InterestType, LeadDetail as LeadDetailType, ProductInterest,
} from '../lib/types'
import {
  Chip, ErrorBox, IntentBadge, ScoreRing, Spinner, formatDate, humanizeSignal,
} from '../components/ui'
import { useLabels } from '../lib/useTaxonomy'

const NO_DEMAND = 'Specific product demand not publicly disclosed.'

const INTEREST_CLASSES: { type: InterestType; label: string; hint: string }[] = [
  { type: 'EXPLICITLY_SEEKING', label: 'Explicitly seeking',
    hint: 'The company publicly asked for these products or suppliers.' },
  { type: 'RECENTLY_ADDED', label: 'Recently added',
    hint: 'New lines or brands the company announced taking on.' },
  { type: 'CURRENTLY_CARRIED', label: 'Currently carried',
    hint: 'Listed on the company\'s own catalogue or brand pages. Not a buying signal on its own.' },
  { type: 'INFERRED_FIT', label: 'Inferred fit',
    hint: 'Adjacent categories that fit what they carry. A hypothesis, not evidence of demand.' },
]

const EXPANSION_SIGNALS = new Set([
  'distribution_center_expansion', 'dealer_network_expansion',
  'acquisition_or_distribution_expansion', 'regional_distribution_expansion',
  'retail_network_expansion', 'acquisition_expansion',
  'private_label_expansion',
])

function Section({ letter, title, subtitle, children }: {
  letter: string; title: string; subtitle?: string; children: ReactNode
}) {
  return (
    <section className="card p-5">
      <h2 className="font-semibold flex items-center gap-2">
        <span className="w-6 h-6 rounded bg-ink-900 text-white text-xs grid
          place-items-center">{letter}</span>
        {title}
      </h2>
      {subtitle && <p className="text-xs text-ink-500 mt-1">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  )
}

function SourceLink({ url, date }: { url: string | null; date?: string | null }) {
  if (!url) return null
  return (
    <div className="text-xs mt-1">
      <a href={url} target="_blank" rel="noreferrer noopener"
        className="text-sky-700 underline break-all">{url}</a>
      {date && <span className="text-ink-400"> · {formatDate(date)}</span>}
    </div>
  )
}

function asList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v) => typeof v === 'string') : []
}

export default function LeadDetail() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<LeadDetailType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const labels = useLabels()

  const load = useCallback(async () => {
    if (!id) return
    try {
      setError(null)
      setData(await api.lead(SERVICE, id))
    } catch (err) {
      setError((err as Error).message)
    }
  }, [id])

  useEffect(() => { void load() }, [load])

  if (error) return <ErrorBox error={error} onRetry={load} />
  if (!data) return <Spinner />

  const { opportunity, company, signals, sources, decision_makers,
    score_breakdown, ai_analysis } = data
  const interests = data.product_interests || []
  const facts = data.company_facts || []
  const dimensions = data.signal_dimensions || {}
  const ai = (ai_analysis || {}) as Record<string, unknown>
  const extra = ((ai.extra as Record<string, unknown>) || ai)
  const buyingSignals = signals.filter((s) =>
    (dimensions[s.signal_type] || 'intent') === 'intent'
    && !EXPANSION_SIGNALS.has(s.signal_type))
  const expansionSignals = signals.filter((s) => EXPANSION_SIGNALS.has(s.signal_type))
  const negativeSignals = signals.filter((s) => dimensions[s.signal_type] === 'negative')
  const lines = score_breakdown.filter((l) => l.points !== 0)
  const summary = data.product_demand_summary || NO_DEMAND
  const location = company.headquarters || company.headquarters_state || company.country

  return (
    <div className="space-y-4">
      <Link to="/leads" className="text-sm text-ink-500 hover:text-ink-900">
        ← Back to leads
      </Link>

      <div className="card p-6 flex gap-6 items-start">
        <ScoreRing score={opportunity.score} size={88} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl font-bold">{company.name || company.domain}</h1>
            <IntentBadge level={opportunity.intent_level} />
            {opportunity.urgency && (
              <Chip tone="red">{opportunity.urgency} urgency</Chip>
            )}
          </div>
          <div className="text-sm text-ink-500 mt-1">
            <a href={company.website || `https://${company.domain}`}
              target="_blank" rel="noreferrer noopener"
              className="underline hover:text-ink-900">{company.domain}</a>
            {location && ` · ${location}`}
            {data.location_unverified && (
              <span className="ml-2"><Chip>location unverified - no address on site</Chip></span>
            )}
          </div>
          <p className="text-sm text-ink-800 mt-3 max-w-3xl font-medium">{summary}</p>
        </div>
        <button className="btn-ghost shrink-0" onClick={async () => {
          setNotice('Re-analysis started…')
          try {
            await api.reanalyze(company.id)
            setTimeout(() => void load(), 5000)
          } catch (err) { setNotice((err as Error).message) }
        }}>Re-analyze</button>
      </div>

      {notice && (
        <div className="card p-3 text-sm bg-sky-50 border-sky-200 text-sky-900">
          {notice}
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <Section letter="A" title="Company profile"
            subtitle="Facts come from the company's own pages; estimates are labelled.">
            <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <Fact label="Company type" value={company.company_type
                ? `${humanizeSignal(company.company_type)}${company.company_type_confidence != null
                  ? ` (${Math.round(company.company_type_confidence * 100)}%)` : ''}`
                : 'Unknown'} />
              <Fact label="Size band" value={company.employee_band
                ? humanizeSignal(company.employee_band) : 'Unknown (not disclosed)'} />
              <Fact label="Employees" value={company.employee_count != null
                ? String(company.employee_count) : 'Not publicly stated'} />
              <Fact label="Headquarters" value={location || 'Unknown'} />
            </dl>
            {company.size_source_url && (
              <div className="text-xs text-ink-500 mt-2">
                Size source: <SourceLink url={company.size_source_url}
                  date={company.size_observed_at} />
              </div>
            )}
            {company.description && (
              <p className="text-sm text-ink-600 mt-3">{company.description}</p>
            )}
            {(company.company_type_evidence?.markers || []).length > 0 && (
              <div className="flex flex-wrap gap-1 mt-3">
                {company.company_type_evidence!.markers!.slice(0, 8).map((m) => (
                  <Chip key={m}>{m}</Chip>
                ))}
              </div>
            )}
            {facts.length > 0 && (
              <table className="w-full text-sm mt-4">
                <tbody>
                  {facts.map((f) => (
                    <tr key={f.id} className="border-b border-ink-100 last:border-0">
                      <td className="py-1.5 pr-3 text-ink-500 align-top w-40">
                        {humanizeSignal(f.fact_type)}
                      </td>
                      <td className="py-1.5 align-top">
                        {f.value}
                        {f.is_estimate && <span className="text-xs text-amber-700"> (estimate)</span>}
                        <SourceLink url={f.source_url} date={f.observed_at} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <Section letter="B" title="Buying intelligence"
            subtitle="Evidence that the distributor is sourcing from suppliers.">
            <p className="text-sm text-ink-700 leading-relaxed">
              {opportunity.reasoning || 'No reasoning recorded yet.'}
            </p>
            {typeof extra.distributor_qualification === 'string' && (
              <div className="text-sm mt-3">
                <span className="label inline">Distributor qualification: </span>
                {humanizeSignal(extra.distributor_qualification)}
                {typeof extra.distributor_qualification_reason === 'string'
                  && ` — ${extra.distributor_qualification_reason}`}
              </div>
            )}
            <SignalList signals={buyingSignals} empty="No live buying signal detected." />
            {negativeSignals.length > 0 && (
              <div className="mt-4">
                <div className="label">Negative / polarity signals</div>
                <SignalList signals={negativeSignals} empty="" negative />
              </div>
            )}
          </Section>

          <Section letter="C" title="Products of interest"
            subtitle="Only products named in a source are listed. Nothing is invented.">
            {interests.length === 0 && (
              <p className="text-sm text-ink-500">{NO_DEMAND}</p>
            )}
            <div className="space-y-4">
              {INTEREST_CLASSES.map((cls) => {
                const rows = interests.filter((i) => i.interest_type === cls.type)
                if (rows.length === 0) return null
                return (
                  <div key={cls.type}>
                    <div className="font-medium text-sm">
                      {labels.interest_types[cls.type] || cls.label} ({rows.length})
                    </div>
                    <div className="text-xs text-ink-500 mb-2">{cls.hint}</div>
                    <div className="space-y-2">
                      {rows.map((row) => <InterestRow key={row.id} row={row} />)}
                    </div>
                  </div>
                )
              })}
            </div>
          </Section>

          <Section letter="D" title="Expansion intelligence"
            subtitle="Warehouses, territories, acquisitions and new lines.">
            <SignalList signals={expansionSignals}
              empty="No dated expansion activity found." />
            {asList(extra.recent_expansion_activity).length > 0 && (
              <ul className="list-disc ml-5 text-sm mt-3 text-ink-700">
                {asList(extra.recent_expansion_activity).map((e) => <li key={e}>{e}</li>)}
              </ul>
            )}
          </Section>

          <Section letter="G" title="Score breakdown"
            subtitle="Every point traces to a weighted signal, its freshness and its evidence.">
            <table className="w-full text-sm">
              <tbody>
                {lines.map((line, i) => (
                  <tr key={i} className="border-b border-ink-100 last:border-0">
                    <td className="py-2 pr-3 align-top">
                      <div className="font-medium">{line.label}</div>
                      {line.detail && (
                        <div className="text-xs text-ink-500 mt-0.5">{line.detail}</div>
                      )}
                    </td>
                    <td className={`py-2 text-right tabular-nums font-semibold
                      align-top w-20 ${line.points < 0 ? 'text-red-600' : 'text-ink-800'}`}>
                      {line.points > 0 ? '+' : ''}{line.points.toFixed(2)}
                    </td>
                  </tr>
                ))}
                <tr className="border-t-2 border-ink-300">
                  <td className="py-2 font-bold">Final score</td>
                  <td className="py-2 text-right font-bold tabular-nums">
                    {opportunity.score.toFixed(1)}
                  </td>
                </tr>
              </tbody>
            </table>
            <div className="grid grid-cols-3 gap-3 mt-4 text-center">
              <Metric label="Deterministic" value={opportunity.deterministic_score.toFixed(1)} />
              <Metric label="AI assessment" value={opportunity.ai_score?.toFixed(1) ?? 'n/a'} />
              <Metric label="Evidence quality" value={opportunity.evidence_score.toFixed(1)} />
            </div>
            {ai_analysis && (
              <details className="mt-4">
                <summary className="text-xs text-ink-500 cursor-pointer">Raw AI analysis</summary>
                <pre className="text-xs bg-ink-50 p-3 rounded overflow-x-auto border
                  border-ink-200 mt-2">{JSON.stringify(ai_analysis, null, 2)}</pre>
              </details>
            )}
          </Section>
        </div>

        <div className="space-y-4">
          <Section letter="E" title="Decision makers"
            subtitle="Purchasing roles from public company pages. No email addresses are collected or stored.">
            <div className="space-y-3">
              {decision_makers.map((person) => (
                <div key={person.id} className="border border-ink-200 rounded-md p-3">
                  <div className="font-semibold text-sm">{person.name}</div>
                  <div className="text-sm text-ink-600">{person.job_title}</div>
                  <div className="mt-2">
                    <Chip tone={person.confidence >= 0.85 ? 'green' : 'default'}>
                      {person.confidence_label ?? 'possible'} · {Math.round(person.confidence * 100)}%
                    </Chip>
                  </div>
                  {person.profile_url && (
                    <a href={person.profile_url} target="_blank" rel="noreferrer noopener"
                      className="text-xs text-sky-700 underline mt-2 block break-all">
                      Source: {person.source}
                    </a>
                  )}
                </div>
              ))}
              {decision_makers.length === 0 && (
                <p className="text-sm text-ink-400">
                  None identified yet. Decision-maker research only runs above
                  the configured score threshold.
                </p>
              )}
              {asList(extra.likely_decision_roles).length > 0 && (
                <div>
                  <div className="label">Likely buying roles</div>
                  <div className="flex flex-wrap gap-1">
                    {asList(extra.likely_decision_roles).map((r) => <Chip key={r}>{r}</Chip>)}
                  </div>
                </div>
              )}
            </div>
          </Section>

          <Section letter="F" title={`Evidence trail (${sources.length})`}>
            <div className="space-y-2 max-h-[32rem] overflow-y-auto">
              {sources.map((source) => (
                <div key={source.id} className="text-sm border-b border-ink-100 pb-2 last:border-0">
                  <div className="flex items-center gap-2">
                    <Chip>{source.source_type}</Chip>
                    <span className="text-xs text-ink-400">
                      {source.published_at
                        ? `published ${formatDate(source.published_at)}`
                        : `undated · seen ${formatDate(source.discovered_at)}`}
                    </span>
                  </div>
                  {source.title && <div className="text-xs mt-1">{source.title}</div>}
                  <a href={source.url} target="_blank" rel="noreferrer noopener"
                    className="text-xs text-sky-700 underline break-all block mt-1">
                    {source.url}
                  </a>
                </div>
              ))}
            </div>
          </Section>

          <section className="card p-5">
            <h2 className="font-semibold mb-3">Rate this lead</h2>
            <p className="text-xs text-ink-500 mb-3">
              Human labels feed the precision metrics in the validation phase.
            </p>
            <div className="flex flex-wrap gap-2">
              {['excellent', 'good', 'maybe', 'bad'].map((label) => (
                <button key={label} className="btn-ghost text-xs"
                  onClick={async () => {
                    await api.reviewLead(SERVICE, opportunity.id, label)
                    setNotice(`Labelled "${label}".`)
                  }}>{label}</button>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function SignalList({ signals, empty, negative = false }: {
  signals: LeadDetailType['signals']; empty: string; negative?: boolean
}) {
  if (signals.length === 0) {
    return empty ? <p className="text-sm text-ink-400 mt-3">{empty}</p> : null
  }
  return (
    <div className="space-y-3 mt-3">
      {signals.map((signal) => (
        <div key={signal.id} className={`border-l-2 pl-3 py-1 ${negative
          ? 'border-red-300' : 'border-ink-300'}`}>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-sm">{humanizeSignal(signal.signal_type)}</span>
            <Chip>{Math.round(signal.confidence * 100)}% confidence</Chip>
            <span className="text-xs text-ink-400">
              detected {formatDate(signal.detected_at)}
              {signal.expires_at && ` · expires ${formatDate(signal.expires_at)}`}
            </span>
          </div>
          {signal.evidence && (
            <blockquote className="text-sm text-ink-600 mt-1 italic">“{signal.evidence}”</blockquote>
          )}
          <SourceLink url={signal.source_url} />
        </div>
      ))}
    </div>
  )
}

function InterestRow({ row }: { row: ProductInterest }) {
  return (
    <div className="border border-ink-200 rounded-md p-3 text-sm">
      <div className="flex flex-wrap items-center gap-1.5">
        {row.category
          ? <Chip tone="green">{row.category}{row.subcategory ? ` › ${row.subcategory}` : ''}</Chip>
          : <span className="text-ink-500">{NO_DEMAND}</span>}
        {row.brand && <Chip tone="blue">{row.brand}</Chip>}
        {row.vehicle_segments.map((v) => <Chip key={v}>{humanizeSignal(v)}</Chip>)}
        {row.vehicle_platforms.map((v) => <Chip key={v}>{v}</Chip>)}
        {Object.values(row.attributes || {}).flat().map((v) => (
          <Chip key={v}>{v}</Chip>
        ))}
        <span className="text-xs text-ink-400 ml-auto">
          {Math.round(row.confidence * 100)}%
        </span>
      </div>
      {row.products.length > 0 && (
        <div className="mt-1 text-ink-700">{row.products.join(', ')}</div>
      )}
      {row.reason && <div className="text-xs text-ink-500 mt-1">{row.reason}</div>}
      {row.evidence && (
        <blockquote className="text-xs text-ink-600 mt-1 italic">“{row.evidence}”</blockquote>
      )}
      <SourceLink url={row.source_url} date={row.published_at || row.event_date} />
    </div>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ink-50 rounded-md p-3 border border-ink-200">
      <div className="text-xs text-ink-500">{label}</div>
      <div className="text-lg font-bold tabular-nums">{value}</div>
    </div>
  )
}
