export type IntentLevel = 'LOW' | 'POSSIBLE' | 'GOOD' | 'STRONG' | 'HOT'

export interface Service {
  id: string; name: string; slug: string
  description: string | null; status: string; config: Record<string, unknown>
}

export interface DashboardStats {
  total_companies: number; total_opportunities: number
  hot_leads: number; strong_leads: number; good_leads: number
  new_leads_7d: number; countries: number; average_score: number
  decision_makers_identified: number; companies_crawled: number
  companies_rejected: number; crawl_success_rate: number
  signals_detected: number; ai_calls: number; ai_failures: number
  estimated_cost_usd: number
  by_country: { country: string; count: number }[]
  by_intent: { intent_level: string; count: number }[]
  by_signal: { signal_type: string; count: number }[]
  by_business_model: { business_model: string; count: number }[]
}

export interface Lead {
  id: string; company_id: string; company_name: string | null
  domain: string; website: string | null; country: string | null
  industry: string | null; platform: string | null
  business_model: string | null
  score: number; intent_level: IntentLevel; urgency: string | null
  likely_need: string[]; signal_types: string[]
  signal_count: number; evidence_count: number
  decision_maker_name: string | null; decision_maker_title: string | null
  decision_maker_confidence: number | null; has_decision_maker: boolean
  last_analyzed: string | null; created_at: string
}

export interface Paginated<T> {
  items: T[]; total: number; page: number; page_size: number; pages: number
}

export interface Signal {
  id: string; signal_type: string; strength: number
  description: string | null; evidence: string | null
  confidence: number; detected_at: string; expires_at: string | null
  source_id: string | null; source_url: string | null
}

export interface Source {
  id: string; source_type: string; url: string; title: string | null
  excerpt: string | null; published_at: string | null
  discovered_at: string; http_status: number | null
}

/** No email field — by design (PRD §20, §35). */
export interface DecisionMaker {
  id: string; name: string; job_title: string | null
  profile_url: string | null; source: string | null
  confidence: number; confidence_label: string | null; role_priority: number
}

export interface ScoreLine {
  label: string; signal_type: string | null
  weight: number; multiplier: number; points: number; detail: string
}

export interface Company {
  id: string; name: string | null; domain: string; website: string | null
  country: string | null; industry: string | null; description: string | null
  is_ecommerce: boolean | null; is_physical_product: boolean | null
  platform: string | null; business_model: string | null
  sales_channels: string[]
  status: string; rejection_reason: string | null
  discovered_via: string | null; last_crawled_at: string | null
  created_at: string
}

export interface Opportunity {
  id: string; company_id: string; service_id: string
  score: number; raw_score: number; deterministic_score: number
  ai_score: number | null; evidence_score: number
  intent_level: IntentLevel; urgency: string | null
  likely_need: string[]; target_country: string[]
  reasoning: string | null; confidence: number | null
  last_analyzed: string | null; created_at: string
}

export interface LeadDetail {
  opportunity: Opportunity; company: Company
  signals: Signal[]; sources: Source[]
  decision_makers: DecisionMaker[]
  score_breakdown: ScoreLine[]
  ai_analysis: Record<string, unknown> | null
}

export interface Health {
  database: { ok: boolean; error: string | null; url_configured: boolean }
  search: { ok: boolean; providers: string[] }
  llm: { ok: boolean; providers: string[] }
  environment: string
}
