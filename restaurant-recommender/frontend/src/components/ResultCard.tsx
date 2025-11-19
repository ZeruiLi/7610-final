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

  return (
    <article className="result-card-minimal" onClick={onClick} role="button" tabIndex={0}>
      <div className="card-image-placeholder" style={{ backgroundColor: placeholderColor }}>
        {/* In a real app, this would be <img src={...} /> */}
        <span className="placeholder-icon">🍽️</span>
      </div>

      <div className="card-content">
        <h3 className="card-title">{place.name}</h3>

        <div className="card-footer">
          <div className="card-rating">
            ⭐ {place.rating ? place.rating.toFixed(1) : 'N/A'}
          </div>
          <div className="card-distance">
            {candidate.distance_miles.toFixed(1)} mi
          </div>
        </div>
      </div>
    </article>
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
