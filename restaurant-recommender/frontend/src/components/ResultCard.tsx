import type { CandidatePayload } from '../types'

interface ResultCardProps {
  candidate: CandidatePayload
  index: number
  onClick: () => void
}

export function ResultCard({ candidate, onClick }: ResultCardProps) {
  const { place } = candidate

  // Generate a consistent pastel color for the placeholder
  const placeholderColor = stringToColor(place.name)
  const tier = candidate.match_tier || (candidate.match_mode?.toLowerCase() === 'relaxed' ? 2 : 1)
  const ratingValue = candidate.derived_rating ?? (candidate.score * 5)
  const modelRating = Math.max(0.5, Math.min(5, candidate.score * 5))
  const ratingSource = candidate.rating_source || 'model_score'

  return (
    <article className="result-card-minimal" onClick={onClick} role="button" tabIndex={0}>
      {/* Tier Badge - top left */}
      <TierBadge tier={tier} />

      <div className="card-image-placeholder" style={{ backgroundColor: placeholderColor }}>
        {/* In a real app, this would be <img src={...} /> */}
        <span className="placeholder-icon">🍽️</span>
      </div>

      <div className="card-content">
        <h3 className="card-title">{place.name}</h3>
        <div className="card-score-row">
          <span className="card-score">Score {candidate.score.toFixed(3)}</span>
          {!candidate.is_open_ok || (candidate.violated_constraints && candidate.violated_constraints.length > 0) ? (
            <span className="card-warning">Needs review</span>
          ) : null}
        </div>

        {/* Match Indicators - Always visible */}
        <div className="card-matches" style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '4px',
          marginTop: '8px',
        }}>
          {candidate.match_cuisine && (
            <span className="match-indicator" style={{
              backgroundColor: '#10b981',
              color: 'white',
              padding: '2px 6px',
              borderRadius: '3px',
              fontSize: '10px',
              fontWeight: '500',
            }}>
              🍽️ Cuisine
            </span>
          )}
          {candidate.match_ambience && (
            <span className="match-indicator" style={{
              backgroundColor: '#8b5cf6',
              color: 'white',
              padding: '2px 6px',
              borderRadius: '3px',
              fontSize: '10px',
              fontWeight: '500',
            }}>
              ✨ Ambience
            </span>
          )}
          {candidate.match_budget && (
            <span className="match-indicator" style={{
              backgroundColor: '#f59e0b',
              color: 'white',
              padding: '2px 6px',
              borderRadius: '3px',
              fontSize: '10px',
              fontWeight: '500',
            }}>
              💰 Budget
            </span>
          )}
          {candidate.match_distance && (
            <span className="match-indicator" style={{
              backgroundColor: '#3b82f6',
              color: 'white',
              padding: '2px 6px',
              borderRadius: '3px',
              fontSize: '10px',
              fontWeight: '500',
            }}>
              📍 Distance
            </span>
          )}
        </div>

        <div className="card-footer">
          <div className="card-rating">
            ⭐ {ratingValue.toFixed(1)} / 5 <span className="card-rating-source">({ratingSource})</span>
            {ratingSource !== 'model_score' && (
              <div className="card-rating-secondary">Model est: {modelRating.toFixed(1)}/5</div>
            )}
          </div>
          <div className="card-distance">
            {candidate.distance_miles.toFixed(1)} mi
          </div>
        </div>
      </div>
    </article>
  )
}

// TierBadge Component - Moved to top-right to avoid overlap
function TierBadge({ tier }: { tier: number }) {
  const isPerfect = tier === 1
  const bgColor = isPerfect ? '#10b981' : '#f59e0b' // green-500 : yellow-500
  const icon = isPerfect ? '✓' : '⚠'
  const text = isPerfect ? 'Perfect' : 'Relaxed'  // Shorter text

  return (
    <div
      style={{
        position: 'absolute',
        top: '8px',
        right: '8px',  // Changed from left to right
        backgroundColor: bgColor,
        color: 'white',
        padding: '3px 7px',
        borderRadius: '4px',
        fontSize: '10px',
        fontWeight: '600',
        zIndex: 10,
        display: 'flex',
        alignItems: 'center',
        gap: '3px',
        boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
      }}
    >
      <span>{icon}</span>
      <span>{text}</span>
    </div>
  )
}

function stringToColor(str: string) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const c = (hash & 0x00FFFFFF).toString(16).toUpperCase();
  return '#' + '00000'.substring(0, 6 - c.length) + c;
}

export default ResultCard
