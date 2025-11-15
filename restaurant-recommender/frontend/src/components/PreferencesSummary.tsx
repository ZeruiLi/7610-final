type Preferences = Record<string, unknown>

interface PreferencesSummaryProps {
  preferences: Preferences
  bbox?: [number, number, number, number]
  latency?: number
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.filter(Boolean).join(', ') || 'Not specified'
  }
  if (value === null || value === undefined || value === '') {
    return 'Not specified'
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value.toString() : 'Not specified'
  }
  return String(value)
}

export function PreferencesSummary({ preferences, bbox, latency }: PreferencesSummaryProps) {
  const fields: Array<{ key: string; label: string }> = [
    { key: 'city', label: 'City' },
    { key: 'area', label: 'Area' },
    { key: 'people', label: 'Party size' },
    { key: 'budget_per_capita', label: 'Budget per guest' },
    { key: 'cuisines', label: 'Cuisines' },
    { key: 'ambiance', label: 'Ambience' },
    { key: 'distance_km', label: 'Radius (km)' },
    { key: 'lang', label: 'Language' },
  ]

  return (
    <section className="preferences-summary" aria-label="preference-summary">
      <h2>Parsed preferences</h2>
      <dl>
        {fields.map(({ key, label }) => (
          <div key={key} className="preferences-summary__item">
            <dt>{label}</dt>
            <dd>{formatValue(preferences[key])}</dd>
          </div>
        ))}
        {bbox ? (
          <div className="preferences-summary__item">
            <dt>Bounding box</dt>
            <dd>
              [{bbox[0].toFixed(4)}, {bbox[1].toFixed(4)}] → [{bbox[2].toFixed(4)}, {bbox[3].toFixed(4)}]
            </dd>
          </div>
        ) : null}
        {typeof latency === 'number' ? (
          <div className="preferences-summary__item">
            <dt>Response time</dt>
            <dd>{latency.toFixed(0)} ms</dd>
          </div>
        ) : null}
        <div className="preferences-summary__item">
          <dt>Must include cuisines</dt>
          <dd>{formatValue(preferences['must_include_cuisines'])}</dd>
        </div>
        <div className="preferences-summary__item">
          <dt>Must exclude cuisines</dt>
          <dd>{formatValue(preferences['must_exclude_cuisines'])}</dd>
        </div>
        <div className="preferences-summary__item">
          <dt>Dining time</dt>
          <dd>{formatValue(preferences['dining_time'])}</dd>
        </div>
        <div className="preferences-summary__item">
          <dt>Strict opening check</dt>
          <dd>{String(preferences['strict_open_check'] ?? true)}</dd>
        </div>
      </dl>
    </section>
  )
}

export default PreferencesSummary
