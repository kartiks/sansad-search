import Cookies from 'js-cookie'

// Recent and saved searches used to live in these cookies. They now live in
// localStorage (lib/searchStorage.js); this module only reads and removes the
// old cookies so their contents can be migrated once.

export const RECENT_COOKIE = 'ss_recent'
export const SAVED_COOKIE = 'ss_saved'

export function readCookie(name) {
  try {
    const raw = Cookies.get(name)
    if (raw == null) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function deleteCookie(name) {
  try {
    Cookies.remove(name)
  } catch {
    // silently fail
  }
}
