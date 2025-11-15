import { useCallback, useMemo, useRef, useState } from 'react'
import { recommend, ApiError } from '../api/recommend'
import type { RecommendResponse } from '../types'
import { SearchBar } from '../components/SearchBar'
import { ResultCard } from '../components/ResultCard'
import { MarkdownView } from '../components/MarkdownView'
import { EmptyState } from '../components/EmptyState'
import { ErrorBar } from '../components/ErrorBar'
import { PreferencesSummary } from '../components/PreferencesSummary'

type TabKey = 'cards' | 'markdown'

const DEFAULT_QUERY = 'Dinner in Seattle Capitol Hill for 2, vegetarian-friendly, under $45 per person'

export function HomePage() {
  const [query, setQuery] = useState('')
  const [data, setData] = useState<RecommendResponse | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [tab, setTab] = useState<TabKey>('cards')
  const [latency, setLatency] = useState<number | null>(null)

  const controllerRef = useRef<AbortController | null>(null)

  const handleSubmit = useCallback(
    async (value: string) => {
      const trimmed = value.trim()
      if (!trimmed) {
        setError(new ApiError('Please enter a query.', { kind: 'http' }))
        return
      }

      controllerRef.current?.abort()
      const controller = new AbortController()
      controllerRef.current = controller

      setPending(true)
      setError(null)
      setTab('cards')
      setLatency(null)

      const started = performance.now()
      try {
        const result = await recommend(trimmed, { signal: controller.signal })
        const duration = performance.now() - started
        setLatency(duration)
        setData(result)
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          return
        }
        if (err instanceof ApiError) {
          setError(err)
        } else {
          setError(new ApiError('Unexpected error. Please try again later.', { kind: 'network', cause: err }))
        }
        setData(null)
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null
        }
        setPending(false)
      }
    },
    [],
  )

  const handleRetry = useCallback(() => {
    const fallback = query.trim().length > 0 ? query : DEFAULT_QUERY
    setQuery(fallback)
    void handleSubmit(fallback)
  }, [handleSubmit, query])

  const handleClear = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setQuery('')
    setData(null)
    setError(null)
    setTab('cards')
  }, [])

  const tabButtons = useMemo(() => {
    const tabs: Array<{ key: TabKey; label: string }> = [
      { key: 'cards', label: 'Card view' },
      { key: 'markdown', label: 'Markdown report' },
    ]
    return tabs
  }, [])

  const hasResults = (data?.candidates.length ?? 0) > 0

  return (
    <section className="home-page">
      <SearchBar
        value={query}
        onChange={setQuery}
        onSubmit={handleSubmit}
        onClear={handleClear}
        pending={pending}
        placeholder={DEFAULT_QUERY}
      />

      {error ? (
        <ErrorBar
          message={error.message}
          detail={error.bodySnippet}
          onRetry={!pending ? handleRetry : undefined}
        />
      ) : null}

      {data ? <PreferencesSummary preferences={data.preferences} bbox={data.bbox} latency={latency ?? undefined} /> : null}

      <div className="view-switcher" role="tablist" aria-label="result-view-toggle">
        {tabButtons.map(({ key, label }) => (
          <button
            key={key}
            role="tab"
            type="button"
            className={key === tab ? 'tab tab--active' : 'tab'}
            aria-selected={key === tab}
            onClick={() => setTab(key)}
            disabled={!hasResults && key !== 'cards'}
          >
            {label}
          </button>
        ))}
      </div>

      <section className="results" aria-live="polite">
        {pending ? (
          <div className="result-skeletons" aria-label="loading recommendations">
            {Array.from({ length: 3 }).map((_, idx) => (
              <div className="result-card result-card--skeleton" key={idx}>
                <div className="skeleton skeleton--title" />
                <div className="skeleton skeleton--line" />
                <div className="skeleton skeleton--line" />
                <div className="skeleton skeleton--line" />
              </div>
            ))}
          </div>
        ) : null}

        {!pending && data && tab === 'cards' && hasResults ? (
          <div className="result-list">
            {data.candidates.map((candidate, idx) => (
              <ResultCard candidate={candidate} index={idx + 1} key={`${candidate.place.name}-${idx}`} />
            ))}
          </div>
        ) : null}

        {!pending && data && tab === 'markdown' && hasResults ? (
          <MarkdownView value={data.recommendations_markdown} />
        ) : null}

        {!pending && (!data || !hasResults) ? (
          <EmptyState
            title="No recommendations yet"
            description={
              data
                ? 'No restaurants matched the request. Try adjusting city, budget, or preferences.'
                : 'Describe what you are looking for above to generate tailored recommendations.'
            }
          />
        ) : null}
      </section>
    </section>
  )
}

export default HomePage
