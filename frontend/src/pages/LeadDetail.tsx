import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import type { LeadDetail as LeadDetailType } from '../lib/types'
import {
  Chip, ErrorBox, IntentBadge, ScoreRing, Spinner, formatDate, humanizeSignal,
} from '../components/ui'

export default function LeadDetail() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<LeadDetailType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    try {
      setError(null)
      setData(await api.lead('3pl', id))
    } catch (err) {
      setError((err as Error).message)
    }
  }, [id])

  useEffect(() => { void load() }, [load])

  if (error) return <ErrorBox error={error} onRetry={load} />
  if (!data) return <Spinner />

  const { opportunity, company, signals, sources, decision_makers,
    score_breakdown, ai_analysis } = data
  const positive = score_breakdown.filter((l) => l.points !== 0)

  return (
    <div className="space-y-4">
      <Link to="/leads" className="text-sm text-ink-500 hover:text-ink-900">
        ← Back to leads
      </Link>

      <div className="card p-6 flex gap-6 items-start">
        <ScoreRing score={opportunity.score} size={88} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl font-bold">
              {company.name || company.domain}
            </h1>
            <IntentBadge level={opportunity.intent_level} />
            {opportunity.urgency && (
              <Chip tone="red">{opportunity.urgency} urgency</Chip>
            )}
          </div>
          <div className="text-sm text-ink-500 mt-1">
            <a href={company.website || `https://${company.domain}`}
              target="_blank" rel="noreferrer noopener"
              className="underline hover:text-ink-900">
              {company.domain}
            </a>
            {company.country && ` · ${company.country}`}
            {company.platform && ` · ${company.platform}`}
            {company.industry && ` · ${company.industry}`}
          </div>
          {company.description && (
            <p className="text-sm text-ink-600 mt-3 max-w-3xl">
              {company.description}
            </p>
          )}
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
          <section className="card p-5">
            <h2 className="font-semibold mb-3">Why is this a lead?</h2>
            <p className="text-sm text-ink-700 leading-relaxed">
              {opportunity.reasoning || 'No reasoning recorded yet.'}
            </p>
            {opportunity.likely_need.length > 0 && (
              <div className="mt-4">
                <div className="label">Likely requirements</div>
                <div className="flex flex-wrap gap-1.5">
                  {opportunity.likely_need.map((need) => (
                    <Chip key={need} tone="green">{need}</Chip>
                  ))}
                </div>
              </div>
            )}
            {opportunity.target_country.length > 0 && (
              <div className="mt-4">
                <div className="label">Target markets</div>
                <div className="flex flex-wrap gap-1.5">
                  {opportunity.target_country.map((market) => (
                    <Chip key={market} tone="blue">{market}</Chip>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="card p-5">
            <h2 className="font-semibold mb-1">Score breakdown</h2>
            <p className="text-xs text-ink-500 mb-4">
              Every point is traceable to a weighted signal, its freshness, and
              its evidence.
            </p>
            <table className="w-full text-sm">
              <tbody>
                {positive.map((line, i) => (
                  <tr key={i} className="border-b border-ink-100 last:border-0">
                    <td className="py-2 pr-3 align-top">
                      <div className="font-medium">{line.label}</div>
                      {line.detail && (
                        <div className="text-xs text-ink-500 mt-0.5">
                          {line.detail}
                        </div>
                      )}
                    </td>
                    <td className={`py-2 text-right tabular-nums font-semibold
                      align-top w-20 ${line.points < 0 ? 'text-red-600'
                        : 'text-ink-800'}`}>
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
              <Metric label="Deterministic"
                value={opportunity.deterministic_score.toFixed(1)} />
              <Metric label="AI assessment"
                value={opportunity.ai_score?.toFixed(1) ?? 'n/a'} />
              <Metric label="Evidence quality"
                value={opportunity.evidence_score.toFixed(1)} />
            </div>
          </section>

          <section className="card p-5">
            <h2 className="font-semibold mb-3">
              Detected signals ({signals.length})
            </h2>
            <div className="space-y-3">
              {signals.map((signal) => (
                <div key={signal.id}
                  className="border-l-2 border-ink-300 pl-3 py-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm">
                      {humanizeSignal(signal.signal_type)}
                    </span>
                    <Chip>{Math.round(signal.confidence * 100)}% confidence</Chip>
                    {signal.expires_at && (
                      <span className="text-xs text-ink-400">
                        expires {formatDate(signal.expires_at)}
                      </span>
                    )}
                  </div>
                  {signal.evidence && (
                    <blockquote className="text-sm text-ink-600 mt-1 italic">
                      “{signal.evidence}”
                    </blockquote>
                  )}
                  {signal.source_url && (
                    <a href={signal.source_url} target="_blank"
                      rel="noreferrer noopener"
                      className="text-xs text-sky-700 underline break-all">
                      {signal.source_url}
                    </a>
                  )}
                </div>
              ))}
              {signals.length === 0 && (
                <p className="text-sm text-ink-400">No signals detected.</p>
              )}
            </div>
          </section>

          {ai_analysis && (
            <section className="card p-5">
              <h2 className="font-semibold mb-3">AI analysis</h2>
              <pre className="text-xs bg-ink-50 p-3 rounded overflow-x-auto
                border border-ink-200">
                {JSON.stringify(ai_analysis, null, 2)}
              </pre>
            </section>
          )}
        </div>

        <div className="space-y-4">
          <section className="card p-5">
            <h2 className="font-semibold mb-1">Decision makers</h2>
            <p className="text-xs text-ink-500 mb-3">
              Identified from public company pages. No email addresses are
              collected or stored.
            </p>
            <div className="space-y-3">
              {decision_makers.map((person) => (
                <div key={person.id}
                  className="border border-ink-200 rounded-md p-3">
                  <div className="font-semibold text-sm">{person.name}</div>
                  <div className="text-sm text-ink-600">{person.job_title}</div>
                  <div className="flex items-center gap-2 mt-2">
                    <Chip tone={person.confidence >= 0.85 ? 'green' : 'default'}>
                      {person.confidence_label ?? 'possible'} ·{' '}
                      {Math.round(person.confidence * 100)}%
                    </Chip>
                  </div>
                  {person.profile_url && (
                    <a href={person.profile_url} target="_blank"
                      rel="noreferrer noopener"
                      className="text-xs text-sky-700 underline mt-2 block
                        break-all">
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
            </div>
          </section>

          <section className="card p-5">
            <h2 className="font-semibold mb-3">
              Evidence ({sources.length})
            </h2>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {sources.map((source) => (
                <div key={source.id} className="text-sm border-b
                  border-ink-100 pb-2 last:border-0">
                  <div className="flex items-center gap-2">
                    <Chip>{source.source_type}</Chip>
                    {source.published_at && (
                      <span className="text-xs text-ink-400">
                        {formatDate(source.published_at)}
                      </span>
                    )}
                  </div>
                  <a href={source.url} target="_blank" rel="noreferrer noopener"
                    className="text-xs text-sky-700 underline break-all block
                      mt-1">
                    {source.url}
                  </a>
                </div>
              ))}
            </div>
          </section>

          <section className="card p-5">
            <h2 className="font-semibold mb-3">Rate this lead</h2>
            <p className="text-xs text-ink-500 mb-3">
              Human labels feed the precision metrics in the validation phase.
            </p>
            <div className="flex flex-wrap gap-2">
              {['excellent', 'good', 'maybe', 'bad'].map((label) => (
                <button key={label} className="btn-ghost text-xs"
                  onClick={async () => {
                    await api.reviewLead('3pl', opportunity.id, label)
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ink-50 rounded-md p-3 border border-ink-200">
      <div className="text-xs text-ink-500">{label}</div>
      <div className="text-lg font-bold tabular-nums">{value}</div>
    </div>
  )
}
