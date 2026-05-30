import { useEffect, useRef } from 'react'

export default function RecentSearchesDropdown({
  entries,
  visible,
  onSelect,
  onDeleteEntry,
  onClearAll,
  onDismiss,
}) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!visible) return undefined

    function handleMouseDown(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        onDismiss()
      }
    }
    function handleKeyDown(e) {
      if (e.key === 'Escape') onDismiss()
    }

    document.addEventListener('mousedown', handleMouseDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleMouseDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [visible, onDismiss])

  if (!visible) return null

  return (
    <div
      className="recent-searches-dropdown"
      ref={containerRef}
      data-testid="recent-searches-dropdown"
    >
      <div className="recent-searches-label">Recent searches</div>

      {entries.length === 0 ? (
        <div
          className="recent-searches-empty"
          data-testid="recent-searches-empty"
        >
          No recent searches
        </div>
      ) : (
        <ul className="recent-searches-list" role="listbox">
          {entries.map((entry) => (
            <li
              key={entry.query}
              className="recent-searches-item"
              data-testid="recent-search-item"
            >
              <button
                type="button"
                className="recent-searches-item-btn"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => onSelect(entry.query)}
                aria-label={`Search for ${entry.query}`}
              >
                <svg
                  className="recent-searches-icon"
                  width="14"
                  height="14"
                  viewBox="0 0 20 20"
                  fill="none"
                  aria-hidden="true"
                >
                  <circle
                    cx="9"
                    cy="9"
                    r="6"
                    stroke="currentColor"
                    strokeWidth="2"
                  />
                  <path
                    d="M14 14L18 18"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
                <span className="recent-searches-query">{entry.query}</span>
              </button>
              <button
                type="button"
                className="recent-searches-delete-btn"
                aria-label={`Remove ${entry.query} from recent searches`}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => onDeleteEntry(entry.query)}
                data-testid="recent-search-delete-btn"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="recent-searches-footer">
        <button
          type="button"
          className="recent-searches-clear-btn"
          onMouseDown={(e) => e.preventDefault()}
          onClick={onClearAll}
          data-testid="recent-search-clear-history"
        >
          Clear history
        </button>
      </div>
    </div>
  )
}
