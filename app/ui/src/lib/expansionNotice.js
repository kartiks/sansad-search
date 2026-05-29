export function parseExpansionNotice(notice) {
  if (!Array.isArray(notice)) return []
  return notice
    .filter((t) => typeof t === 'string' && t.trim().length > 0)
    .map((t) => t.trim())
}

export function formatExpansionNotice(notice) {
  const parsed = parseExpansionNotice(notice)
  if (parsed.length === 0) return ''
  return `Also searching for: ${parsed.join(', ')}`
}

export function hasExpansion(notice) {
  return parseExpansionNotice(notice).length > 0
}
