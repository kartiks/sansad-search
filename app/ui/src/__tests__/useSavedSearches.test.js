import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'


import { useSavedSearches, sanitizeStoredFilters } from '../hooks/useSavedSearches.js'
import Cookies from 'js-cookie'
import { defaultFilterState } from '../lib/filterState.js'

function makeFilters(overrides = {}) {
  return { ...defaultFilterState(), ...overrides }
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

function disableStorage() {
  vi.spyOn(Object.getPrototypeOf(window.localStorage), 'setItem').mockImplementation(() => {
    throw new Error('SecurityError')
  })
}

function stored(key) {
  return JSON.parse(window.localStorage.getItem(key))
}

describe('sanitizeStoredFilters', () => {
  it('returns default state for null input', () => {
    expect(sanitizeStoredFilters(null)).toEqual(defaultFilterState())
  })

  it('passes through valid filter values unchanged', () => {
    const filters = makeFilters({ sources: ['LS', 'RS'] })
    const result = sanitizeStoredFilters(filters)
    expect(result.sources).toEqual(['LS', 'RS'])
  })

  it('removes unrecognised source values', () => {
    const filters = makeFilters({ sources: ['LS', 'UNKNOWN_BODY'] })
    const result = sanitizeStoredFilters(filters)
    expect(result.sources).toEqual(['LS'])
  })

  it('falls back to all sources when all stored sources are unrecognised', () => {
    const filters = makeFilters({ sources: ['FAKE1', 'FAKE2'] })
    const result = sanitizeStoredFilters(filters)
    expect(result.sources).toEqual(defaultFilterState().sources)
  })

  it('removes unrecognised proceeding_type values — stale filter test', () => {
    const filters = makeFilters({
      proceeding_types: ['debate', 'LEGACY_TYPE_FROM_OLD_SCHEMA'],
    })
    const result = sanitizeStoredFilters(filters)
    expect(result.proceeding_types).toEqual(['debate'])
  })

  it('falls back to all proceeding_types when all stored types are unrecognised', () => {
    const filters = makeFilters({ proceeding_types: ['LEGACY_TYPE'] })
    const result = sanitizeStoredFilters(filters)
    expect(result.proceeding_types).toEqual(defaultFilterState().proceeding_types)
  })

  it('does not throw when stored filter has unrecognised keys', () => {
    const stored = {
      sources: ['LS'],
      proceeding_types: ['debate'],
      date_from: '2020-01-01',
      date_to: '2024-12-31',
      speaker: 'John',
      session: 'Budget Session 2023',
      unknownKey: 'ignored',
    }
    expect(() => sanitizeStoredFilters(stored)).not.toThrow()
    const result = sanitizeStoredFilters(stored)
    expect(result.date_from).toBe('2020-01-01')
    expect(result.speaker).toBe('John')
    expect(result).not.toHaveProperty('unknownKey')
  })
})

describe('useSavedSearches — saveSearch', () => {
  it('adds a new entry with name defaulting to query text', () => {
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'water rights', filters: defaultFilterState() })
    })
    expect(result.current.entries).toHaveLength(1)
    expect(result.current.entries[0].name).toBe('water rights')
    expect(result.current.entries[0].query).toBe('water rights')
  })

  it('accepts a custom name', () => {
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'water rights', filters: defaultFilterState(), name: 'My search' })
    })
    expect(result.current.entries[0].name).toBe('My search')
  })

  it('truncates name at 60 characters', () => {
    const longName = 'x'.repeat(65)
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'test', filters: defaultFilterState(), name: longName })
    })
    expect(result.current.entries[0].name).toHaveLength(60)
  })

  it('accepts a name of exactly 60 characters', () => {
    const name60 = 'a'.repeat(60)
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'test', filters: defaultFilterState(), name: name60 })
    })
    expect(result.current.entries[0].name).toHaveLength(60)
  })

  it('same query saved twice creates two separate entries', () => {
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'budget', filters: defaultFilterState() })
    })
    act(() => {
      result.current.saveSearch({ query: 'budget', filters: defaultFilterState() })
    })
    expect(result.current.entries).toHaveLength(2)
    expect(result.current.entries[0].id).not.toBe(result.current.entries[1].id)
  })

  it('stores the filter state exactly', () => {
    const filters = makeFilters({
      sources: ['RS'],
      proceeding_types: ['starred_question'],
      date_from: '2020-01-01',
    })
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'test', filters })
    })
    expect(result.current.entries[0].filters.sources).toEqual(['RS'])
    expect(result.current.entries[0].filters.proceeding_types).toEqual(['starred_question'])
    expect(result.current.entries[0].filters.date_from).toBe('2020-01-01')
  })

  it('persists saved entries to localStorage', () => {
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'test', filters: defaultFilterState() })
    })
    expect(stored('ss_saved')[0].query).toBe('test')
  })

  it('stores only non-default filters', () => {
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'a', filters: defaultFilterState() })
      result.current.saveSearch({
        query: 'b',
        filters: makeFilters({ sources: ['RS'], speaker: 'Nehru' }),
      })
    })
    const entries = stored('ss_saved')
    expect(entries[0].filters).toEqual({})
    expect(entries[1].filters).toEqual({ sources: ['RS'], speaker: 'Nehru' })
  })

  it('keeps all 20 entries, well past the old 4 KB cookie limit', () => {
    const { result } = renderHook(() => useSavedSearches())
    for (let i = 0; i < 20; i++) {
      act(() => {
        result.current.saveSearch({
          query: `query ${i} ${'x'.repeat(200)}`,
          filters: makeFilters({ sources: ['LS'], speaker: 'Speaker Name', date_from: '2001-01-01' }),
        })
      })
    }
    expect(JSON.stringify(stored('ss_saved')).length).toBeGreaterThan(4096)
    const { result: reloaded } = renderHook(() => useSavedSearches())
    expect(reloaded.current.entries).toHaveLength(20)
    expect(reloaded.current.entries[19].filters.sources).toEqual(['LS'])
    expect(reloaded.current.entries[19].filters.proceeding_types).toEqual(
      defaultFilterState().proceeding_types
    )
  })

  it('stores a 500-character query field at full length without truncation', () => {
    const longQuery = 'a'.repeat(500)
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({
        query: longQuery,
        filters: defaultFilterState(),
        name: 'long query test',
      })
    })
    expect(result.current.entries[0].query).toBe(longQuery)
    expect(result.current.entries[0].query.length).toBe(500)
  })
})

describe('useSavedSearches — atLimit', () => {
  it('atLimit is false when fewer than 20 entries exist', () => {
    const { result } = renderHook(() => useSavedSearches())
    expect(result.current.atLimit).toBe(false)
  })

  it('atLimit is true when exactly 20 entries exist', () => {
    const existing = Array.from({ length: 20 }, (_, i) => ({
      id: `id-${i}`,
      name: `search ${i}`,
      query: `query ${i}`,
      filters: defaultFilterState(),
      timestamp: i,
    }))
    window.localStorage.setItem('ss_saved', JSON.stringify(existing))
    const { result } = renderHook(() => useSavedSearches())
    expect(result.current.atLimit).toBe(true)
  })

  it('does not create a 21st entry when at limit', () => {
    const existing = Array.from({ length: 20 }, (_, i) => ({
      id: `id-${i}`,
      name: `search ${i}`,
      query: `query ${i}`,
      filters: defaultFilterState(),
      timestamp: i,
    }))
    window.localStorage.setItem('ss_saved', JSON.stringify(existing))
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'extra', filters: defaultFilterState() })
    })
    expect(result.current.entries).toHaveLength(20)
    expect(result.current.entries.find((e) => e.query === 'extra')).toBeUndefined()
  })
})

describe('useSavedSearches — deleteEntry', () => {
  it('removes the entry with matching id', () => {
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'alpha', filters: defaultFilterState() })
    })
    act(() => {
      result.current.saveSearch({ query: 'beta', filters: defaultFilterState() })
    })
    const idToDelete = result.current.entries[0].id
    act(() => {
      result.current.deleteEntry(idToDelete)
    })
    expect(result.current.entries.find((e) => e.id === idToDelete)).toBeUndefined()
    expect(result.current.entries).toHaveLength(1)
  })
})

describe('useSavedSearches — renameEntry', () => {
  it('updates the name of the matching entry', () => {
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'water rights', filters: defaultFilterState() })
    })
    const id = result.current.entries[0].id
    act(() => {
      result.current.renameEntry(id, 'My water rights search')
    })
    expect(result.current.entries[0].name).toBe('My water rights search')
  })

  it('truncates renamed name at 60 characters', () => {
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'test', filters: defaultFilterState() })
    })
    const id = result.current.entries[0].id
    act(() => {
      result.current.renameEntry(id, 'z'.repeat(70))
    })
    expect(result.current.entries[0].name).toHaveLength(60)
  })
})

describe('useSavedSearches — storage', () => {
  it('returns empty entries when storage is blocked', () => {
    disableStorage()
    const { result } = renderHook(() => useSavedSearches())
    expect(result.current.entries).toHaveLength(0)
    expect(result.current.storageEnabled).toBe(false)
  })

  it('does not save when storage is blocked', () => {
    disableStorage()
    const { result } = renderHook(() => useSavedSearches())
    act(() => {
      result.current.saveSearch({ query: 'test', filters: defaultFilterState() })
    })
    expect(result.current.entries).toHaveLength(0)
  })

  it('migrates the legacy ss_saved cookie (full filter objects) once', () => {
    const legacy = [
      {
        id: 'old-1',
        name: 'old',
        query: 'water',
        filters: makeFilters({ sources: ['CA'] }),
        timestamp: 1,
      },
    ]
    Cookies.set('ss_saved', JSON.stringify(legacy))
    const { result } = renderHook(() => useSavedSearches())
    expect(result.current.entries).toHaveLength(1)
    expect(result.current.entries[0].filters.sources).toEqual(['CA'])
    expect(Cookies.get('ss_saved')).toBeUndefined()
  })
})
