import { useCallback } from 'react'
import type { FormEvent } from 'react'
import classNames from 'classnames'

interface SearchBarProps {
  value: string
  onChange: (next: string) => void
  onSubmit: (value: string) => void
  onClear?: () => void
  placeholder?: string
  pending?: boolean
}

export function SearchBar({ value, onChange, onSubmit, onClear, placeholder, pending }: SearchBarProps) {
  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      onSubmit(value.trim())
    },
    [onSubmit, value],
  )

  return (
    <form className="search-bar" onSubmit={handleSubmit} aria-label="restaurant-recommendation-search">
      <label htmlFor="query" className="search-bar__label">
        Describe your dining request
      </label>
      <textarea
        id="query"
        className="search-bar__input"
        rows={3}
        value={value}
        placeholder={placeholder ?? 'Example: Dinner in Seattle Capitol Hill, vegetarian-friendly, under $45 per person'}
        onChange={(event) => onChange(event.target.value)}
        aria-multiline="true"
        disabled={pending}
      />
      <div className="search-bar__actions">
        <button
          type="submit"
          className={classNames('btn', 'btn-primary')}
          disabled={pending || value.trim().length === 0}
        >
          {pending ? 'Searching…' : 'Find restaurants'}
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => onClear?.()}
          disabled={pending || value.length === 0}
        >
          Clear
        </button>
      </div>
    </form>
  )
}

export default SearchBar
