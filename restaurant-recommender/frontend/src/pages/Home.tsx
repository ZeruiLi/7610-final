import { useCallback, useEffect, useRef, useState } from 'react'
import { recommendStream, ApiError, type StreamedResult } from '../api/recommend'
import type { CandidatePayload } from '../types'
import { SearchBar } from '../components/SearchBar'
import { ResultCard } from '../components/ResultCard'
import { ErrorBar } from '../components/ErrorBar'
import { PreferencesSummary } from '../components/PreferencesSummary'
import { EmptyState } from '../components/EmptyState'
import { RestaurantDetailModal } from '../components/RestaurantDetailModal'

const DEFAULT_QUERY = 'Dinner in Seattle Capitol Hill for 2, vegetarian-friendly, under $45 per person'

export function HomePage() {
  const [query, setQuery] = useState('')
  const [streamedResults, setStreamedResults] = useState<StreamedResult[]>([])
  const [preferences, setPreferences] = useState<Record<string, unknown> | null>(null)
  const [bbox, setBbox] = useState<[number, number, number, number] | null>(null)
  const [pending, setPending] = useState(false)
  const [streamComplete, setStreamComplete] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [sessionId, setSessionId] = useState<string>('')
  const [latency, setLatency] = useState<number | null>(null)
  const [selectedCandidate, setSelectedCandidate] = useState<CandidatePayload | null>(null)
  const [visibleCount, setVisibleCount] = useState(8)
  const [userLocation, setUserLocation] = useState<{ lat: number; lon: number } | null>(null)
  const [locationHint, setLocationHint] = useState<string>('')
  const [lastQuery, setLastQuery] = useState<string>('')

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
      setLastQuery(trimmed)
      setStreamedResults([])
      setStreamComplete(false)
      setVisibleCount(8)

      controllerRef.current?.abort()
      const controller = new AbortController()
      controllerRef.current = controller

      const started = performance.now()

      try {
        // Use streaming API
        for await (const event of recommendStream(trimmed, {
          signal: controller.signal,
          sessionId: sessionId,
          limit: 24,
          userLocation: userLocation ?? undefined,
        })) {
          if (event.type === 'metadata') {
            // First event: metadata with preferences and bbox
            setPreferences(event.preferences)
            setBbox(event.bbox)
            console.info('[Home] Received metadata', event.preferences)
          } else if (event.type === 'candidate') {
            // Subsequent events: candidates
            setStreamedResults(prev => [...prev, event])

            // Add small delay for initial batch visual effect
            if (event.is_initial_batch && event.index < 7) {
              await new Promise(resolve => setTimeout(resolve, 100))
            }
          }
        }

        setLatency(performance.now() - started)
        setStreamComplete(true)
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
    [sessionId, userLocation],
  )

  const handleClear = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setQuery('')
    setStreamedResults([])
    setPreferences(null)
    setBbox(null)
    setStreamComplete(false)
    setError(null)
    setLastQuery('')
    // Reset session on clear to start fresh context
    setSessionId(`sess-${Date.now()}-${Math.random().toString(36).slice(2)}`)
  }, [])

  const handleUseLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setLocationHint('Geolocation not supported in this browser.')
      return
    }
    setLocationHint('Requesting location...')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude })
        setLocationHint(`Using current location (${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)})`)
      },
      (err) => {
        console.error('geolocation error', err)
        setLocationHint('Unable to get location. Please allow permission or try again.')
      },
      { enableHighAccuracy: false, timeout: 8000 },
    )
  }, [])

  const hasResults = streamedResults.length > 0
  const visibleCandidates = streamedResults.slice(0, visibleCount).map(r => r.candidate)

  return (
    <section className="home-page">
      {/* Sticky Preferences - OUTSIDE scroll container */}
      {(preferences || bbox) && (
        <div className="preferences-bar-container">
          <PreferencesSummary preferences={preferences || {}} bbox={bbox || [0, 0, 0, 0]} latency={latency ?? undefined} />
        </div>
      )}

      {/* Main Scrollable Content Area */}
      <div className="dashboard-content" ref={resultsContainerRef}>
        {/* State A: Empty / Welcome */}
        {streamedResults.length === 0 && !pending && !error && (
          <div className="welcome-container">
            <EmptyState
              title="Welcome to Tango"
              description="Describe what you are looking for below to get started. I can help you find the perfect restaurant."
            />
          </div>
        )}

        {/* State B: Results */}
        {(streamedResults.length > 0 || pending || error) && (
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
            {!pending && hasResults && (
              <>
                <div className="result-grid">
                  {visibleCandidates.map((candidate, idx) => (
                    <ResultCard
                      candidate={candidate}
                      index={idx + 1}
                      key={`${candidate.place.name}-${idx}`}
                      onClick={() => setSelectedCandidate(candidate)}
                    />
                  ))}
                </div>

                {visibleCount < streamedResults.length && (
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

            {!pending && streamComplete && !hasResults && (
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
          placeholder={streamedResults.length > 0 ? "Refine your search (e.g. 'cheaper', 'in Bellevue')..." : DEFAULT_QUERY}
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
