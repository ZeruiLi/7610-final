interface EmptyStateProps {
  title: string
  description?: string
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
    </div>
  )
}

export default EmptyState
