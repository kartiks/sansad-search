import Cookies from 'js-cookie'

export const RECENT_COOKIE = 'ss_recent'
export const SAVED_COOKIE = 'ss_saved'
export const MAX_COMBINED_BYTES = 4096

export function areCookiesEnabled() {
  try {
    const key = '__cc__'
    Cookies.set(key, '1')
    const ok = Cookies.get(key) === '1'
    Cookies.remove(key)
    return ok
  } catch {
    return false
  }
}

export function readCookie(name) {
  try {
    const raw = Cookies.get(name)
    if (raw == null) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function writeCookie(name, data, options = {}) {
  try {
    Cookies.set(name, JSON.stringify(data), options)
  } catch {
    // silently fail
  }
}

export function deleteCookie(name) {
  try {
    Cookies.remove(name)
  } catch {
    // silently fail
  }
}

function byteSize(data) {
  const str = JSON.stringify(data)
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(str).length
  }
  let len = 0
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i)
    len += c < 128 ? 1 : c < 2048 ? 2 : 3
  }
  return len
}

// Trims oldest recent entries (entries are newest-first, so pop() removes oldest)
// until combined byte size of both cookies is within MAX_COMBINED_BYTES.
// Never touches savedEntries.
export function trimRecentToFit(recentEntries, savedEntries) {
  const saved = savedEntries || []
  let recent = [...recentEntries]
  while (recent.length > 0 && byteSize(recent) + byteSize(saved) > MAX_COMBINED_BYTES) {
    recent.pop()
  }
  return recent
}
