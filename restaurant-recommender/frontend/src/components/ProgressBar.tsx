import React, { useEffect, useState } from 'react'

export type LoadingStage = 'idle' | 'parsing' | 'searching' | 'enriching' | 'complete'

interface ProgressBarProps {
    stage: LoadingStage
}

export function ProgressBar({ stage }: ProgressBarProps) {
    const [percent, setPercent] = useState(0)
    const [message, setMessage] = useState('')

    useEffect(() => {
        let targetPercent = 0
        let msg = ''

        switch (stage) {
            case 'parsing':
                targetPercent = 30
                msg = 'Understanding your request...'
                break
            case 'searching':
                targetPercent = 60
                msg = 'Searching for best matches...'
                break
            case 'enriching':
                targetPercent = 90
                msg = 'Fetching details & reviews...'
                break
            case 'complete':
                targetPercent = 100
                msg = 'Done'
                break
            default:
                targetPercent = 0
                msg = ''
        }

        setPercent(targetPercent)
        setMessage(msg)
    }, [stage])

    if (stage === 'idle' || stage === 'complete') return null

    return (
        <div className="progress-bar-container" style={{ margin: '1rem 0', textAlign: 'center' }}>
            <div className="progress-text" style={{ marginBottom: '0.5rem', color: '#666', fontSize: '0.9rem' }}>
                {message}
            </div>
            <div className="progress-track" style={{
                background: '#eee',
                height: '6px',
                borderRadius: '3px',
                overflow: 'hidden',
                maxWidth: '400px',
                margin: '0 auto'
            }}>
                <div
                    className="progress-fill"
                    style={{
                        width: `${percent}%`,
                        height: '100%',
                        background: 'var(--primary-color, #ff4757)',
                        transition: 'width 0.5s ease-out'
                    }}
                />
            </div>
        </div>
    )
}
