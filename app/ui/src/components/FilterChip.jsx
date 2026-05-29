export default function FilterChip({ label, onRemove }) {
  return (
    <span className="filter-chip" data-testid="filter-chip">
      <span className="filter-chip-label">{label}</span>
      <button
        type="button"
        className="filter-chip-remove"
        aria-label={`Remove filter: ${label}`}
        onClick={onRemove}
        data-testid="filter-chip-remove"
      >
        ×
      </button>
    </span>
  )
}
