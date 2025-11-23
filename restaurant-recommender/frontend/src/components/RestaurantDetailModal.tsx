import React from 'react'
import type { CandidatePayload } from '../types'

interface RestaurantDetailModalProps {
    candidate: CandidatePayload
    onClose: () => void
}

export function RestaurantDetailModal({ candidate, onClose }: RestaurantDetailModalProps) {
    const { place } = candidate

    // Prevent clicks inside the modal from closing it
    const handleContentClick = (e: React.MouseEvent) => {
        e.stopPropagation()
    }

    return (
        <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
            <div className="modal-content" onClick={handleContentClick}>
                <button className="modal-close-btn" onClick={onClose} aria-label="Close details">
                    ×
                </button>

                <div className="modal-header-image">
                    {/* Placeholder gradient since we don't have real images */}
                    <div className="placeholder-image-large" style={{ background: `linear-gradient(135deg, ${stringToColor(place.name)} 0%, #f5f5f5 100%)` }} />
                </div>

                <div className="modal-body">
                    <h2 className="modal-title">{place.name}</h2>
                    <div className="modal-meta">
                        <span className="modal-rating">⭐ {(candidate.derived_rating ?? candidate.score * 5).toFixed(1)} / 5 ({candidate.rating_source || 'model'})</span>
                        {candidate.rating_source !== 'model_score' && (
                            <>
                                <span className="modal-dot">·</span>
                                <span className="modal-rating">Model est {Math.max(0.5, Math.min(5, candidate.score * 5)).toFixed(1)}/5</span>
                            </>
                        )}
                        <span className="modal-dot">·</span>
                        <span className="modal-distance">{candidate.distance_miles.toFixed(1)} mi</span>
                        <span className="modal-dot">·</span>
                        <span className="modal-address">{place.address}</span>
                    </div>
                    <div className="modal-meta" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
                        <span className="modal-score-chip">Score {candidate.score.toFixed(3)}</span>
                        <span className={`modal-match-chip ${candidate.match_mode === 'relaxed' ? 'chip-relaxed' : 'chip-strict'}`}>
                            {candidate.match_mode === 'relaxed' ? 'Relaxed match' : 'Strict match'}
                        </span>
                        {!candidate.is_open_ok || (candidate.violated_constraints && candidate.violated_constraints.length > 0) ? (
                            <span className="modal-warning-chip">Does not fully meet all constraints</span>
                        ) : (
                            <span className="modal-good-chip">Meets key constraints</span>
                        )}
                    </div>

                    <div className="modal-tags">
                        {candidate.primary_tags.map(tag => (
                            <span key={tag} className="tag">{tag}</span>
                        ))}
                    </div>

                    <hr className="modal-divider" />

                    {candidate.why_matched.length > 0 && (
                        <section className="modal-section">
                            <h3>Why it fits</h3>
                            <ul className="modal-list">
                                {candidate.why_matched.map((item, idx) => <li key={idx}>{item}</li>)}
                            </ul>
                        </section>
                    )}

                    {candidate.highlights.length > 0 && (
                        <section className="modal-section">
                            <h3>Highlights</h3>
                            <ul className="modal-list">
                                {candidate.highlights.map((item, idx) => <li key={idx}>{item}</li>)}
                            </ul>
                        </section>
                    )}

                    {candidate.signature_dishes.length > 0 && (
                        <section className="modal-section">
                            <h3>Signature Dishes</h3>
                            <div className="dish-tags">
                                {candidate.signature_dishes.map((dish, idx) => (
                                    <span key={idx} className="dish-tag">{dish}</span>
                                ))}
                            </div>
                        </section>
                    )}

                    {candidate.violated_constraints.length > 0 && (
                        <section className="modal-section">
                            <h3>Constraints not fully met</h3>
                            <ul className="modal-list warning">
                                {candidate.violated_constraints.map((item, idx) => <li key={idx}>{item}</li>)}
                            </ul>
                        </section>
                    )}

                    {candidate.debug_scores && Object.keys(candidate.debug_scores).length > 0 && (
                        <section className="modal-section">
                            <h3>Score breakdown</h3>
                            <ul className="modal-list">
                                {Object.entries(candidate.debug_scores).map(([k, v]) => (
                                    <li key={k}>{k}: {v.toFixed(3)}</li>
                                ))}
                            </ul>
                        </section>
                    )}

                    {candidate.risks.length > 0 && (
                        <section className="modal-section">
                            <h3>Things to know</h3>
                            <ul className="modal-list warning">
                                {candidate.risks.map((item, idx) => <li key={idx}>{item}</li>)}
                            </ul>
                        </section>
                    )}

                    <div className="modal-actions">
                        {place.website && (
                            <a href={place.website} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-block">
                                Visit Website
                            </a>
                        )}
                        {place.datasource_url && (
                            <a href={place.datasource_url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-block">
                                View on Map
                            </a>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}

// Helper to generate consistent pastel colors from string
function stringToColor(str: string) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const c = (hash & 0x00FFFFFF).toString(16).toUpperCase();
    return '#' + '00000'.substring(0, 6 - c.length) + c;
}
