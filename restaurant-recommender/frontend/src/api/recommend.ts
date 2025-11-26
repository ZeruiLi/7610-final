import type { RecommendRequestPayload, RecommendResponse, CandidatePayload } from '../types'

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
    ['reliability_score', 'distance_km', 'distance_miles', 'source_trust_score', 'derived_rating'].every((field) =>
      typeof candidate[field] === 'number',
    ) &&
    typeof candidate.source_hits === 'number' &&
    typeof candidate.is_open_ok === 'boolean' &&
    typeof candidate.rating_source === 'string' &&
    typeof candidate.match_mode === 'string' &&
    Array.isArray(candidate.violated_constraints ?? [])
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

export async function recommend(
  query: string,
  opts?: { signal?: AbortSignal; sessionId?: string; limit?: number; userLocation?: { lat: number; lon: number } },
): Promise<RecommendResponse> {
  const payload: RecommendRequestPayload = {
    query,
    session_id: opts?.sessionId,
    limit: opts?.limit ?? 8,
    user_lat: opts?.userLocation?.lat,
    user_lon: opts?.userLocation?.lon,
  }
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

// NEW: Streaming API types and function
export interface StreamedMetadata {
  type: 'metadata'
  preferences: Record<string, unknown>
  bbox: [number, number, number, number]
}

export interface StreamedResult {
  type: 'candidate'
  status?: 'partial' | 'full'
  index: number
  total: number
  tier: number
  candidate: CandidatePayload
  is_initial_batch: boolean
}

export type StreamEvent = StreamedMetadata | StreamedResult

export async function* recommendStream(
  query: string,
  opts?: { signal?: AbortSignal; sessionId?: string; limit?: number; userLocation?: { lat: number; lon: number } },
): AsyncGenerator<StreamEvent, void, unknown> {
  const payload: RecommendRequestPayload = {
    query,
    session_id: opts?.sessionId,
    limit: opts?.limit ?? 24,
    user_lat: opts?.userLocation?.lat,
    user_lon: opts?.userLocation?.lon,
  }

  let response: Response
  try {
    response = await fetch(`${baseUrl}/recommend-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
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

  if (!response.ok) {
    const snippet = (await response.text()).slice(0, 200)
    throw new ApiError(`后端返回错误（${response.status}）`, {
      kind: 'http',
      status: response.status,
      bodySnippet: snippet,
    })
  }

  if (!response.body) {
    throw new ApiError('响应body为空', { kind: 'parse' })
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataJson = line.slice(6)
          try {
            const data = JSON.parse(dataJson) as Record<string, unknown>

            if (data.type === 'complete') {
              console.info('[recommendStream] complete')
              return
            }

            if (data.type === 'error') {
              throw new ApiError(`流式错误: ${data.message}`, { kind: 'http' })
            }

            if (data.type === 'metadata') {
              // Metadata event with preferences and bbox
              yield data as unknown as StreamedMetadata
              continue
            }

            if (data.type === 'candidate') {
              // Regular candidate event
              yield data as unknown as StreamedResult
            }
          } catch (error) {
            if (error instanceof ApiError) throw error
            console.error('[recommendStream] parse_error', dataJson, error)
            throw new ApiError('解析SSE事件失败', { kind: 'parse', cause: error })
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

