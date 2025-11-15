import classNames from 'classnames'

interface ErrorBarProps {
  message: string
  detail?: string
  onRetry?: () => void
}

export function ErrorBar({ message, detail, onRetry }: ErrorBarProps) {
  return (
    <div className={classNames('alert', 'alert-danger')} role="alert">
      <div>
        <strong>{message}</strong>
        {detail ? <p className="alert-detail">{detail}</p> : null}
      </div>
      {onRetry ? (
        <button type="button" className="btn btn-danger" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  )
}

export default ErrorBar
