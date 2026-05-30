import { useState, useCallback } from 'react'
import {
  areCookiesEnabled,
  readCookie,
  writeCookie,
  SAVED_COOKIE,
} from '../lib/cookie.js'
import { defaultFilterState } from '../lib/filterState.js'
import { ALL_SOURCES, ALL_PROCEEDING_TYPES } from '../lib/constants.js'

const SAVED_MAX = 20
const NAME_MAX_LEN = 60

// Sanitizes a stored filter object: removes unrecognised values.
// If all sources or proceeding_types become empty after filtering,
// falls back to defaults so search always executes.
export function sanitizeStoredFilters(stored) {
  const def = defaultFilterState()
  if (!stored || typeof stored !== 'object') return def

  const sources = Array.isArray(stored.sources)
    ? stored.sources.filter((s) => ALL_SOURCES.includes(s))
    : null
  const proceedingTypes = Array.isArray(stored.proceeding_types)
    ? stored.proceeding_types.filter((pt) => ALL_PROCEEDING_TYPES.includes(pt))
    : null

  return {
    sources: sources && sources.length > 0 ? sources : def.sources,
    proceeding_types:
      proceedingTypes && proceedingTypes.length > 0
        ? proceedingTypes
        : def.proceeding_types,
    date_from: stored.date_from || null,
    date_to: stored.date_to || null,
    speaker: stored.speaker || null,
    session: stored.session || null,
  }
}

export function useSavedSearches() {
  const [cookiesEnabled] = useState(() => areCookiesEnabled())

  const [entries, setEntries] = useState(() => {
    if (!cookiesEnabled) return []
    const data = readCookie(SAVED_COOKIE)
    return Array.isArray(data) ? data : []
  })

  const saveSearch = useCallback(
    ({ query, filters, name }) => {
      if (!cookiesEnabled) return
      setEntries((prev) => {
        if (prev.length >= SAVED_MAX) return prev
        const saveName = (name || query || '').slice(0, NAME_MAX_LEN)
        const entry = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          name: saveName,
          query: query || '',
          filters: filters || defaultFilterState(),
          timestamp: Date.now(),
        }
        const next = [...prev, entry]
        writeCookie(SAVED_COOKIE, next) // no expires — persistent
        return next
      })
    },
    [cookiesEnabled]
  )

  const deleteEntry = useCallback(
    (id) => {
      if (!cookiesEnabled) return
      setEntries((prev) => {
        const next = prev.filter((e) => e.id !== id)
        writeCookie(SAVED_COOKIE, next)
        return next
      })
    },
    [cookiesEnabled]
  )

  const renameEntry = useCallback(
    (id, newName) => {
      if (!cookiesEnabled) return
      const trimmed = (newName || '').slice(0, NAME_MAX_LEN)
      setEntries((prev) => {
        const next = prev.map((e) =>
          e.id === id ? { ...e, name: trimmed } : e
        )
        writeCookie(SAVED_COOKIE, next)
        return next
      })
    },
    [cookiesEnabled]
  )

  const atLimit = entries.length >= SAVED_MAX

  return { entries, cookiesEnabled, atLimit, saveSearch, deleteEntry, renameEntry }
}
