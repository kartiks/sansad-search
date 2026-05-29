// Formatting helpers for the F07 indexing status surfaces (homepage strip and
// full panel). Centralised so both surfaces render counts and dates identically.

const MONTHS_LONG = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const MONTHS_SHORT = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

// Integer count with thousands separators, e.g. 198000 -> "198,000".
export function formatCount(n) {
  const num = Number(n)
  if (!Number.isFinite(num)) return '0'
  return num.toLocaleString('en-US')
}

// Ingestion timestamp -> "DD Month YYYY" (UTC) or "Never" when never run.
export function formatLongDate(raw) {
  if (!raw) return 'Never'
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return 'Never'
  return `${d.getUTCDate()} ${MONTHS_LONG[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

// Single date -> "Mon YYYY" (UTC), or "" when missing/invalid.
export function formatMonthYear(raw) {
  if (!raw) return ''
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return ''
  return `${MONTHS_SHORT[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

// Per-source date coverage -> "Mon YYYY – Mon YYYY" (en-dash), collapsing to a
// single value when both ends fall in the same month, or "" when neither end
// is known (caller renders the zero-record row instead).
export function formatCoverage(dateFrom, dateTo) {
  const a = formatMonthYear(dateFrom)
  const b = formatMonthYear(dateTo)
  if (a && b) return a === b ? a : `${a} – ${b}`
  return a || b || ''
}
