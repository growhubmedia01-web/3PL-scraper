import type {
  DashboardStats, Health, Lead, LeadDetail, Paginated, Service,
} from './types'

const BASE = import.meta.env.VITE_API_BASE_URL || ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* noop */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export interface LeadFilters {
  q?: string; country?: string; intent?: string; urgency?: string
  industry?: string; platform?: string; business_model?: string
  signal?: string
  min_score?: number; has_decision_maker?: boolean
  discovered_within_days?: number
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

  stats: (service = '3pl') =>
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

  runDiscovery: (service_slug = '3pl', limit?: number, country?: string) =>
    request<{ message: string; task_id: string | null }>('/api/discovery/run', {
      method: 'POST',
      body: JSON.stringify({ service_slug, limit, country, run_async: true }),
    }),

  processQueue: (limit = 25) =>
    request<{ message: string }>(`/api/pipeline/process-queue${qs({ limit })}`, {
      method: 'POST', body: JSON.stringify({ service_slug: '3pl' }),
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
      body: JSON.stringify({ service_slug: '3pl', force_crawl: true }),
    }),

  runs: () => request<Array<Record<string, unknown>>>('/api/pipeline/runs'),

  exportUrl: (service: string, filters: LeadFilters = {}) =>
    `${BASE}/api/export${qs({ service, ...filters } as Record<string, unknown>)}`,
}
