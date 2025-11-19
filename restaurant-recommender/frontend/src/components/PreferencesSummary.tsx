import React from 'react'

type Preferences = Record<string, unknown>

interface PreferencesSummaryProps {
  preferences: Preferences
  bbox?: [number, number, number, number]
  latency?: number
}

function formatValue(value: unknown): string | null {
  if (Array.isArray(value)) {
    const filtered = value.filter(Boolean)
    return filtered.length > 0 ? filtered.join(', ') : null
  }
  if (value === null || value === undefined || value === '') {
    return null
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value.toString() : null
  }
  return String(value)
}

export function PreferencesSummary({ preferences }: PreferencesSummaryProps) {
  // We only show key fields that are actually set to keep it compact
  const summaryItems: Array<{ label: string; value: string }> = []

  const addIfSet = (label: string, key: string, suffix: string = '') => {
    const val = formatValue(preferences[key])
    if (val && val !== 'Not specified') {
      summaryItems.push({ label, value: val + suffix })
    }
  }

  addIfSet('📍', 'city')
  addIfSet('📍 Area', 'area')
  addIfSet('🍽️', 'cuisines')
  addIfSet('🌶️', 'must_include_cuisines')  // Add spicy/required cuisines
  addIfSet('🚫', 'must_exclude_cuisines')
  addIfSet('💰', 'budget_per_capita', '/person')
  addIfSet('👥', 'people', ' ppl')
  addIfSet('✨', 'ambiance')

  // Special handling for radius if it's not default (e.g. 3)
  const radius = preferences['distance_km']
  if (typeof radius === 'number' && radius !== 3) {
    summaryItems.push({ label: '📏', value: `${radius}km` })
  }

  // Fallback if nothing is parsed (rare)
  if (summaryItems.length === 0) {
    summaryItems.push({ label: '🔍', value: 'Searching...' })
  }

  return (
    <div className="preferences-bar">
      <div className="preferences-scroll">
        {summaryItems.map((item, idx) => (
          <div key={idx} className="preference-chip">
            <span className="preference-chip__label">{item.label}</span>
            <span className="preference-chip__value">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default PreferencesSummary
