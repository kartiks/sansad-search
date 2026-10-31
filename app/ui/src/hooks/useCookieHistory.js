// Recent searches (F08). Stored in localStorage (lib/searchStorage.js); the
// hook keeps its old name to avoid churn across pages and tests.

import { useState, useCallback } from 'react'
import {
  isStorageAvailable,
  readList,
  writeList,
  RECENT_KEY,
} from '../lib/searchStorage.js'

export const RECENT_MAX = 10
export const RECENT_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000

function isValidEntry(e) {
  return e && typeof e.query === 'string' && e.query && typeof e.timestamp === 'number'
}

// Drops malformed entries and entries older than 30 days.
function freshEntries(list, now = Date.now()) {
  return list
    .filter(isValidEntry)
    .filter((e) => now - e.timestamp <= RECENT_MAX_AGE_MS)
    .slice(0, RECENT_MAX)
}

export function useCookieHistory() {
  const [storageEnabled] = useState(() => isStorageAvailable())

  const [entries, setEntries] = useState(() => {
    if (!storageEnabled) return []
    return freshEntries(readList(RECENT_KEY))
  })

  const recordSearch = useCallback(
    (query) => {
      if (!storageEnabled || !query) return
      setEntries((prev) => {
        const now = Date.now()
        const filtered = prev.filter((e) => e.query !== query)
        const next = freshEntries([{ query, timestamp: now }, ...filtered], now)
        writeList(RECENT_KEY, next)
        return next
      })
    },
    [storageEnabled]
  )

  const deleteEntry = useCallback(
    (query) => {
      if (!storageEnabled) return
      setEntries((prev) => {
        const next = prev.filter((e) => e.query !== query)
        writeList(RECENT_KEY, next)
        return next
      })
    },
    [storageEnabled]
  )

  const clearAll = useCallback(() => {
    if (!storageEnabled) return
    // Write [] rather than removing the key, so the one-time cookie
    // migration never runs again.
    writeList(RECENT_KEY, [])
    setEntries([])
  }, [storageEnabled])

  return { entries, storageEnabled, recordSearch, deleteEntry, clearAll }
}
