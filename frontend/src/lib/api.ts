import type {
  DashboardStats, Health, Lead, LeadDetail, Paginated, Service, Taxonomy,
} from './types'

const BASE = import.meta.env.VITE_API_BASE_URL || ''

/** The service this dashboard shows. The legacy '3pl' service is retained
 *  in the database; set VITE_SERVICE_SLUG=3pl to view it. */
export const SERVICE: string =
  import.meta.env.VITE_SERVICE_SLUG || 'powersports_aftermarket_sourcing'

const MAX_RETRIES = 3
const RETRY_DELAY_MS = 1000 // doubles each attempt: 1s, 2s, 4s

async function request<T>(path: string, init?: RequestInit, attempt = 0): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
      ...init,
    })

    // Retry on 500/503 — Render cold-start returns these transiently
    if ((res.status === 500 || res.status === 503) && attempt < MAX_RETRIES) {
      await new Promise(r => setTimeout(r, RETRY_DELAY_MS * Math.pow(2, attempt)))
      return request<T>(path, init, attempt + 1)
    }

    if (!res.ok) {
      let detail = res.statusText
      try { detail = (await res.json()).detail ?? detail } catch { /* noop */ }
      throw new Error(`${res.status}: ${detail}`)
    }
    return res.json() as Promise<T>
  } catch (err) {
    // Retry on network failures (ERR_FAILED = server not yet awake)
    if (attempt < MAX_RETRIES && err instanceof TypeError) {
      await new Promise(r => setTimeout(r, RETRY_DELAY_MS * Math.pow(2, attempt)))
      return request<T>(path, init, attempt + 1)
    }
    throw err
  }
}


export interface LeadFilters {
  q?: string; country?: string; intent?: string; urgency?: string
  industry?: string; platform?: string; business_model?: string
  signal?: string
  min_score?: number; has_decision_maker?: boolean
  discovered_within_days?: number
  state?: string; employee_band?: string; company_type?: string
  product_category?: string; interest_type?: string
  vehicle_segment?: string; signal_within_days?: number
  sort?: string; page?: number; page_size?: number
}

function qs(params: Record<string, unknown>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  })
  const str = search.toString()
  return str ? `?${str}` : ''
}

export const api = {
  services: () => request<Service[]>('/api/services'),

  stats: (service = SERVICE) =>
    request<DashboardStats>(`/api/stats${qs({ service })}`),

  health: () => request<Health>('/api/stats/health'),

  leads: (service: string, filters: LeadFilters = {}) =>
    request<Paginated<Lead>>(
      `/api/services/${service}/opportunities${qs(filters as Record<string, unknown>)}`),

  lead: (service: string, id: string) =>
    request<LeadDetail>(`/api/services/${service}/opportunities/${id}`),

  reviewLead: (service: string, id: string, label: string, notes?: string) =>
    request(`/api/services/${service}/opportunities/${id}/review`, {
      method: 'POST', body: JSON.stringify({ label, notes }),
    }),

  runDiscovery: (service_slug = SERVICE, limit?: number, country?: string, tier?: number, max_queries?: number) =>
    request<{ message: string; task_id: string | null }>('/api/discovery/run', {
      method: 'POST',
      body: JSON.stringify({ service_slug, limit, country, tier, max_queries, run_async: true }),
    }),

  processQueue: (limit = 25) =>
    request<{ message: string }>(`/api/pipeline/process-queue${qs({ limit })}`, {
      method: 'POST', body: JSON.stringify({ service_slug: SERVICE }),
    }),

  addCompany: (url: string) =>
    request<{ message: string; result: { company_id: string } | null }>(
      '/api/companies/add', {
        method: 'POST',
        body: JSON.stringify({ url, analyze_now: true }),
      }),

  reanalyze: (companyId: string) =>
    request<{ message: string }>(`/api/analyze/${companyId}`, {
      method: 'POST',
      body: JSON.stringify({ service_slug: SERVICE, force_crawl: true }),
    }),

  taxonomy: (service = SERVICE) =>
    request<Taxonomy>(`/api/services/${service}/taxonomy`),

  runs: () => request<Array<Record<string, unknown>>>('/api/pipeline/runs'),

  exportUrl: (service: string, filters: LeadFilters = {}) =>
    `${BASE}/api/export${qs({ service, ...filters } as Record<string, unknown>)}`,
}
