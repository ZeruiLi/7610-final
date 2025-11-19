import { useCallback, useEffect, useRef, useState } from 'react'
import { recommend, ApiError } from '../api/recommend'
import type { RecommendResponse, CandidatePayload } from '../types'
import { SearchBar } from '../components/SearchBar'
import { ResultCard } from '../components/ResultCard'
import { ErrorBar } from '../components/ErrorBar'
import { PreferencesSummary } from '../components/PreferencesSummary'
import { EmptyState } from '../components/EmptyState'
import { RestaurantDetailModal } from '../components/RestaurantDetailModal'

const DEFAULT_QUERY = 'Dinner in Seattle Capitol Hill for 2, vegetarian-friendly, under $45 per person'

export function HomePage() {
  const [query, setQuery] = useState('')
  const [data, setData] = useState<RecommendResponse | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [sessionId, setSessionId] = useState<string>('')
  const [latency, setLatency] = useState<number | null>(null)
  const [selectedCandidate, setSelectedCandidate] = useState<CandidatePayload | null>(null)
  const [visibleCount, setVisibleCount] = useState(8)

  const controllerRef = useRef<AbortController | null>(null)
  const resultsContainerRef = useRef<HTMLDivElement>(null)

  // Initialize session ID on mount
  useEffect(() => {
    setSessionId(`sess-${Date.now()}-${Math.random().toString(36).slice(2)}`)
  }, [])

  const handleSubmit = useCallback(
    async (value: string) => {
      const trimmed = value.trim()
      if (!trimmed) return

      setPending(true)
      setError(null)
      setLatency(null)

      controllerRef.current?.abort()
      const controller = new AbortController()
      controllerRef.current = controller

      const started = performance.now()

      try {
        const result = await recommend(trimmed, {
          signal: controller.signal,
          sessionId: sessionId,
          limit: 24 // Fetch more to allow "Load More"
        })
        setLatency(performance.now() - started)
        setData(result)
        setVisibleCount(8) // Reset visible count on new search
        setQuery('') // Clear input after successful submission

        // Scroll to top of results
        if (resultsContainerRef.current) {
          resultsContainerRef.current.scrollTop = 0
        }

      } catch (err) {
        if ((err as Error).name === 'AbortError') return

        if (err instanceof ApiError) {
          setError(err)
        } else {
          setError(new ApiError('Unexpected error. Please try again later.', { kind: 'network', cause: err }))
        }
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null
        }
        setPending(false)
      }
    },
    [sessionId],
  )

  const handleClear = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setQuery('')
    setData(null)
    setError(null)
    // Reset session on clear to start fresh context
    setSessionId(`sess-${Date.now()}-${Math.random().toString(36).slice(2)}`)
  }, [])

  const hasResults = (data?.candidates.length ?? 0) > 0

  return (
    <section className="home-page">
      {/* Sticky Preferences - OUTSIDE scroll container */}
      {data && (
        <div className="preferences-bar-container">
          <PreferencesSummary preferences={data.preferences} bbox={data.bbox} latency={latency ?? undefined} />
        </div>
      )}

      {/* Main Scrollable Content Area */}
      <div className="dashboard-content" ref={resultsContainerRef}>
        {/* State A: Empty / Welcome */}
        {!data && !pending && !error && (
          <div className="welcome-container">
            <EmptyState
              title="Welcome to Tango"
              description="Describe what you are looking for below to get started. I can help you find the perfect restaurant."
            />
          </div>
        )}

        {/* State B: Results */}
        {(data || pending || error) && (
          <div className="results-container">
            {/* Error Bar */}
            {error && (
              <div style={{ padding: '1rem' }}>
                <ErrorBar
                  message={error.message}
                  detail={error.bodySnippet}
                  onRetry={() => { }}
                />
              </div>
            )}

            {/* Loading Skeletons */}
            {pending && (
              <div className="result-grid">
                {Array.from({ length: 8 }).map((_, idx) => (
                  <div className="result-card-minimal skeleton-card" key={idx}>
                    <div className="skeleton skeleton--image" />
                    <div className="skeleton skeleton--text" />
                    <div className="skeleton skeleton--text-short" />
                  </div>
                ))}
              </div>
            )}

            {/* Card Grid */}
            {!pending && data && hasResults && (
              <>
                <div className="result-grid">
                  {data.candidates.slice(0, visibleCount).map((candidate, idx) => (
                    <ResultCard
                      candidate={candidate}
                      index={idx + 1}
                      key={`${candidate.place.name}-${idx}`}
                      onClick={() => setSelectedCandidate(candidate)}
                    />
                  ))}
                </div>

                {visibleCount < data.candidates.length && (
                  <div style={{ textAlign: 'center', padding: '2rem 1rem' }}>
                    <button
                      className="btn btn-secondary"
                      onClick={() => setVisibleCount(prev => prev + 8)}
                    >
                      Load more
                    </button>
                  </div>
                )}
              </>
            )}

            {!pending && data && !hasResults && (
              <div style={{ padding: '2rem', textAlign: 'center', color: '#666' }}>
                <p>No restaurants matched your criteria. Try adjusting your request.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Sticky Footer Input */}
      <div className="chat-input-area">
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={handleSubmit}
          onClear={handleClear}
          pending={pending}
          placeholder={data ? "Refine your search (e.g. 'cheaper', 'in Bellevue')..." : DEFAULT_QUERY}
        />
      </div>

      {/* Detail Modal */}
      {selectedCandidate && (
        <RestaurantDetailModal
          candidate={selectedCandidate}
          onClose={() => setSelectedCandidate(null)}
        />
      )}
    </section>
  )
}

export default HomePage
