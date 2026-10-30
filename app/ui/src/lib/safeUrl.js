// Returns the URL only if it is an absolute http(s) URL, else null. Used for
// source links from the API so a `javascript:` or `data:` URL can never end
// up in an href.
export function safeHttpUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const trimmed = value.trim()
    const url = new URL(trimmed)
    return url.protocol === 'http:' || url.protocol === 'https:' ? trimmed : null
  } catch {
    return null
  }
}
