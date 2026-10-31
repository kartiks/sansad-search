// localStorage persistence for recent and saved searches (F08).
//
// These used to be cookies, but a cookie silently stops saving once it passes
// about 4 KB, which full filter objects reached after roughly 7 saved
// searches. localStorage has no such tight limit.
//
// Every access is wrapped in try/catch: storage can be disabled, full, or
// throw on access (private mode, blocked site data). Callers get [] / false
// and the app keeps working without history.

import { readCookie, deleteCookie } from './cookie.js'

export const RECENT_KEY = 'ss_recent'
export const SAVED_KEY = 'ss_saved'

function getStorage() {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null
  } catch {
    return null
  }
}

export function isStorageAvailable() {
  const storage = getStorage()
  if (!storage) return false
  try {
    const key = '__ss_test__'
    storage.setItem(key, '1')
    const ok = storage.getItem(key) === '1'
    storage.removeItem(key)
    return ok
  } catch {
    return false
  }
}

export function writeList(key, list) {
  const storage = getStorage()
  if (!storage) return false
  try {
    storage.setItem(key, JSON.stringify(list))
    return true
  } catch {
    return false
  }
}

// One-time move of the old cookie into localStorage. Runs only when the
// localStorage key has never been written, and deletes the cookie once the
// copy has been saved.
function migrateFromCookie(key) {
  const data = readCookie(key)
  if (data == null) return []
  const list = Array.isArray(data) ? data : []
  if (writeList(key, list)) deleteCookie(key)
  return list
}

export function readList(key) {
  const storage = getStorage()
  if (!storage) return []
  let raw
  try {
    raw = storage.getItem(key)
  } catch {
    return []
  }
  if (raw == null) return migrateFromCookie(key)
  try {
    const data = JSON.parse(raw)
    return Array.isArray(data) ? data : []
  } catch {
    return []
  }
}
