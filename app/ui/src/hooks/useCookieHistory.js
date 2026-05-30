import { useState, useCallback } from 'react'
import {
  areCookiesEnabled,
  readCookie,
  writeCookie,
  deleteCookie,
  trimRecentToFit,
  RECENT_COOKIE,
  SAVED_COOKIE,
} from '../lib/cookie.js'

const RECENT_MAX = 10
const RECENT_EXPIRY_DAYS = 30

export function useCookieHistory() {
  const [cookiesEnabled] = useState(() => areCookiesEnabled())

  const [entries, setEntries] = useState(() => {
    if (!cookiesEnabled) return []
    const data = readCookie(RECENT_COOKIE)
    return Array.isArray(data) ? data : []
  })

  const recordSearch = useCallback(
    (query) => {
      if (!cookiesEnabled || !query) return
      setEntries((prev) => {
        const now = Date.now()
        const filtered = prev.filter((e) => e.query !== query)
        const next = [{ query, timestamp: now }, ...filtered].slice(0, RECENT_MAX)
        const savedData = readCookie(SAVED_COOKIE) || []
        const trimmed = trimRecentToFit(next, savedData)
        writeCookie(RECENT_COOKIE, trimmed, { expires: RECENT_EXPIRY_DAYS })
        return trimmed
      })
    },
    [cookiesEnabled]
  )

  const deleteEntry = useCallback(
    (query) => {
      if (!cookiesEnabled) return
      setEntries((prev) => {
        const next = prev.filter((e) => e.query !== query)
        const savedData = readCookie(SAVED_COOKIE) || []
        const trimmed = trimRecentToFit(next, savedData)
        writeCookie(RECENT_COOKIE, trimmed, { expires: RECENT_EXPIRY_DAYS })
        return trimmed
      })
    },
    [cookiesEnabled]
  )

  const clearAll = useCallback(() => {
    if (!cookiesEnabled) return
    deleteCookie(RECENT_COOKIE)
    setEntries([])
  }, [cookiesEnabled])

  return { entries, cookiesEnabled, recordSearch, deleteEntry, clearAll }
}
