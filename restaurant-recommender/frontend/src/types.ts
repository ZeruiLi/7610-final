export interface PlacePayload {
  name: string
  address?: string | null
  lon: number
  lat: number
  website?: string | null
  opening_hours?: string | null
  datasource_url?: string | null
  tags: string[]
  rating?: number | null
}

export interface DetailSource {
  title?: string
  name?: string
  url?: string
  description?: string
  [key: string]: unknown
}

export interface CandidatePayload {
  place: PlacePayload
  score: number
  reason: string
  pros: string[]
  cons: string[]
  highlights: string[]
  signature_dishes: string[]
  why_matched: string[]
  risks: string[]
  detail_sources: DetailSource[]
  match_cuisine: boolean
  match_ambience: boolean
  match_budget: boolean
  match_distance: boolean
  match_popularity: boolean
  primary_tags: string[]
  reliability_score: number
  distance_km: number
  distance_miles: number
  source_hits: number
  source_trust_score: number
}

export interface RecommendResponse {
  recommendations_markdown: string
  candidates: CandidatePayload[]
  preferences: Record<string, unknown>
  bbox: [number, number, number, number]
}

export interface RecommendRequestPayload {
  query: string
  session_id?: string
  limit?: number
}

export type RecommendConfigHeader = Record<string, unknown>

export interface ApiResult<T> {
  data: T
  durationMs: number
}
