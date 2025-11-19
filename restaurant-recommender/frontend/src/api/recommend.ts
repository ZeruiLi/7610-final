import type { RecommendRequestPayload, RecommendResponse } from '../types'

const DEFAULT_BASE_URL = 'http://localhost:8010'

const baseUrl = (() => {
  const raw = (import.meta.env.VITE_API_BASE as string | undefined) ?? DEFAULT_BASE_URL
  return raw.replace(/\/$/, '')
})()

export class ApiError extends Error {
  readonly status?: number
  readonly bodySnippet?: string
  readonly kind: 'network' | 'http' | 'parse'

  constructor(message: string, opts: { status?: number; bodySnippet?: string; kind: 'network' | 'http' | 'parse'; cause?: unknown }) {
    super(message)
    this.name = 'ApiError'
    this.status = opts.status
    this.bodySnippet = opts.bodySnippet
    this.kind = opts.kind
    if (opts.cause instanceof Error) {
      this.cause = opts.cause
    }
  }
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function isCandidate(value: unknown): boolean {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  const place = candidate.place as Record<string, unknown> | undefined
  if (!place || typeof place.name !== 'string') return false
  if (typeof place.lon !== 'number' || typeof place.lat !== 'number') return false
  if (typeof candidate.score !== 'number') return false
  if (typeof candidate.reason !== 'string') return false

  const stringListFields = ['pros', 'cons', 'highlights', 'signature_dishes', 'why_matched', 'risks'] as const
  return stringListFields.every((key) => {
    const arr = candidate[key]
    return Array.isArray(arr) ? isStringArray(arr) : Array.isArray(arr) || arr === undefined
  }) &&
    Array.isArray(candidate.primary_tags ?? []) &&
    ['reliability_score', 'distance_km', 'distance_miles', 'source_trust_score'].every((field) =>
      typeof candidate[field] === 'number',
    ) &&
    typeof candidate.source_hits === 'number'
}

export function isRecommendResponse(value: unknown): value is RecommendResponse {
  if (typeof value !== 'object' || value === null) return false
  const obj = value as Record<string, unknown>
  if (typeof obj.recommendations_markdown !== 'string') return false
  if (!Array.isArray(obj.candidates)) return false
  if (!obj.candidates.every((item) => isCandidate(item))) return false
  if (!Array.isArray(obj.bbox) || obj.bbox.length !== 4) return false
  return true
}

export async function recommend(query: string, opts?: { signal?: AbortSignal; sessionId?: string; limit?: number }): Promise<RecommendResponse> {
  const payload: RecommendRequestPayload = { query, session_id: opts?.sessionId, limit: opts?.limit ?? 8 }
  const started = performance.now()
  let response: Response

  try {
    response = await fetch(`${baseUrl}/recommend`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: opts?.signal,
    })
  } catch (error) {
    throw new ApiError('网络请求失败，请检查后端服务是否启动。', {
      kind: 'network',
      cause: error,
    })
  }

  const duration = performance.now() - started

  if (!response.ok) {
    const snippet = (await response.text()).slice(0, 200)
    console.error('[recommend] http_error', response.status, `${duration.toFixed(1)}ms`, snippet)
    throw new ApiError(`后端返回错误（${response.status}）`, {
      kind: 'http',
      status: response.status,
      bodySnippet: snippet,
    })
  }

  try {
    const data = (await response.json()) as unknown
    if (!isRecommendResponse(data)) {
      console.error('[recommend] schema_mismatch', data)
      throw new ApiError('响应格式不符合预期。', { kind: 'parse' })
    }
    console.info('[recommend] success', `${duration.toFixed(1)}ms`, data.candidates.length)
    return data
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }
    throw new ApiError('解析响应失败。', { kind: 'parse', cause: error })
  }
}
