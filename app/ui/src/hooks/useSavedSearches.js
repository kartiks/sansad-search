// Saved searches (F08). Stored in localStorage (lib/searchStorage.js) with
// only the non-default filters, so entries stay small.

import { useState, useCallback } from 'react'
import {
  isStorageAvailable,
  readList,
  writeList,
  SAVED_KEY,
} from '../lib/searchStorage.js'
import {
  compactFilters,
  defaultFilterState,
  sanitizeStoredFilters,
} from '../lib/filterState.js'

export { sanitizeStoredFilters }

export const SAVED_MAX = 20
const NAME_MAX_LEN = 60

// In memory, entries carry the full filter state.
function fromStored(e) {
  return { ...e, filters: sanitizeStoredFilters(e.filters) }
}

function toStored(e) {
  return { ...e, filters: compactFilters(e.filters) }
}

function persist(entries) {
  writeList(SAVED_KEY, entries.map(toStored))
}

function isValidEntry(e) {
  return e && typeof e.id === 'string' && typeof e.query === 'string'
}

export function useSavedSearches() {
  const [storageEnabled] = useState(() => isStorageAvailable())

  const [entries, setEntries] = useState(() => {
    if (!storageEnabled) return []
    return readList(SAVED_KEY).filter(isValidEntry).map(fromStored)
  })

  const saveSearch = useCallback(
    ({ query, filters, name }) => {
      if (!storageEnabled) return
      setEntries((prev) => {
        if (prev.length >= SAVED_MAX) return prev
        const saveName = (name || query || '').slice(0, NAME_MAX_LEN)
        const entry = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          name: saveName,
          query: query || '',
          filters: sanitizeStoredFilters(filters || defaultFilterState()),
          timestamp: Date.now(),
        }
        const next = [...prev, entry]
        persist(next)
        return next
      })
    },
    [storageEnabled]
  )

  const deleteEntry = useCallback(
    (id) => {
      if (!storageEnabled) return
      setEntries((prev) => {
        const next = prev.filter((e) => e.id !== id)
        persist(next)
        return next
      })
    },
    [storageEnabled]
  )

  const renameEntry = useCallback(
    (id, newName) => {
      if (!storageEnabled) return
      const trimmed = (newName || '').slice(0, NAME_MAX_LEN)
      setEntries((prev) => {
        const next = prev.map((e) =>
          e.id === id ? { ...e, name: trimmed } : e
        )
        persist(next)
        return next
      })
    },
    [storageEnabled]
  )

  const atLimit = entries.length >= SAVED_MAX

  return { entries, storageEnabled, atLimit, saveSearch, deleteEntry, renameEntry }
}
