import type { CandidatePayload } from '../types'

interface ResultCardProps {
  candidate: CandidatePayload
  index: number
}

const MATCH_FLAGS: Array<{ key: keyof CandidatePayload; label: string }> = [
  { key: 'match_cuisine', label: 'Cuisine match' },
  { key: 'match_ambience', label: 'Ambience match' },
  { key: 'match_budget', label: 'Budget noted' },
  { key: 'match_distance', label: 'Within range' },
]

function formatSources(candidate: CandidatePayload) {
  return (candidate.detail_sources || []).map((source, index) => {
    const title = (source.title as string) || (source.name as string) || `Source ${index + 1}`
    const weight = typeof source.weight === 'number' ? ` (${source.weight.toFixed(2)})` : ''
    if (typeof source.url === 'string' && source.url.length > 0) {
      return (
        <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer">
          {title}
          {weight}
        </a>
      )
    }
    return (
      <span key={`${title}-${index}`}>{title}</span>
    )
  })
}

export function ResultCard({ candidate, index }: ResultCardProps) {
  const { place } = candidate
  const dishes = candidate.signature_dishes.filter(Boolean).slice(0, 4)
  const highlights = candidate.highlights.filter(Boolean).slice(0, 3)
  const whyMatched = candidate.why_matched.filter(Boolean).slice(0, 3)
  const risks = candidate.risks.filter(Boolean).slice(0, 3)
  const tagList = candidate.primary_tags.length ? candidate.primary_tags : place.tags.slice(0, 4)

  return (
    <article className="result-card" aria-label={`Recommendation ${index}: ${place.name}`}>
      <header className="result-card__header">
        <div>
          <h3>
            {index}. {place.name}
          </h3>
          <p className="result-card__address">{place.address ?? 'Address unavailable'}</p>
          <div className="result-card__tags">
            {tagList.map((tag) => (
              <span className="tag" key={tag}>
                {tag}
              </span>
            ))}
          </div>
        </div>
        <div className="result-card__score-block">
          <span className="result-card__score" aria-label="Recommendation score">
            {candidate.score.toFixed(2)}
          </span>
          <span className="result-card__meta">
            {candidate.source_hits} sources · trust {candidate.source_trust_score.toFixed(2)}
          </span>
        </div>
      </header>

      <section className="result-card__section result-card__section--stats">
        <div>
          <strong>Distance</strong>
          <span>{candidate.distance_miles.toFixed(1)} mi ({candidate.distance_km.toFixed(1)} km)</span>
        </div>
        <div>
          <strong>Average rating</strong>
          <span>{place.rating ? `${place.rating.toFixed(1)}★` : 'n/a'}</span>
        </div>
        <div>
          <strong>Website</strong>
          <span>{place.website ? 'Available' : 'Unavailable'}</span>
        </div>
      </section>

      {highlights.length > 0 && (
        <section className="result-card__section">
          <h4>Highlights</h4>
          <ul className="result-card__bullets">
            {highlights.map((item, idx) => (
              <li key={`hi-${idx}`}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {whyMatched.length > 0 && (
        <section className="result-card__section">
          <h4>Why it fits</h4>
          <ul className="result-card__bullets">
            {whyMatched.map((item, idx) => (
              <li key={`why-${idx}`}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {dishes.length > 0 && (
        <section className="result-card__section">
          <h4>Signature dishes</h4>
          <p>{dishes.join(', ')}</p>
        </section>
      )}

      {candidate.pros.length > 0 && (
        <section className="result-card__section">
          <h4>Pros</h4>
          <ul className="result-card__bullets">
            {candidate.pros.map((item, idx) => (
              <li key={`pro-${idx}`}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {risks.length > 0 && (
        <section className="result-card__section">
          <h4>Risks</h4>
          <ul className="result-card__bullets result-card__bullets--warning">
            {risks.map((item, idx) => (
              <li key={`risk-${idx}`}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="result-card__section result-card__section--meta">
        <div className="result-card__matches">
          {MATCH_FLAGS.filter(({ key }) => candidate[key]).map(({ key, label }) => (
            <span className="tag tag--match" key={key}>
              {label}
            </span>
          ))}
        </div>
        <div className="result-card__links">
          {place.datasource_url && (
            <a href={place.datasource_url} target="_blank" rel="noopener noreferrer">
              View on map
            </a>
          )}
          {place.website && (
            <a href={place.website} target="_blank" rel="noopener noreferrer">
              Official website
            </a>
          )}
          {formatSources(candidate)}
        </div>
      </section>
    </article>
  )
}

export default ResultCard
