import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'


import { useCookieHistory } from '../hooks/useCookieHistory.js'
import Cookies from 'js-cookie'

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

describe('useCookieHistory — recordSearch', () => {
  it('adds a new entry to the list', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => {
      result.current.recordSearch('freedom of speech')
    })
    expect(result.current.entries).toHaveLength(1)
    expect(result.current.entries[0].query).toBe('freedom of speech')
    expect(result.current.entries[0].timestamp).toBeDefined()
  })

  it('places the new entry at the front (newest first)', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('first'))
    act(() => result.current.recordSearch('second'))
    expect(result.current.entries[0].query).toBe('second')
    expect(result.current.entries[1].query).toBe('first')
  })

  it('deduplicates: same query 3 times results in exactly 1 entry', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('parliament'))
    act(() => result.current.recordSearch('parliament'))
    act(() => result.current.recordSearch('parliament'))
    expect(result.current.entries).toHaveLength(1)
    expect(result.current.entries[0].query).toBe('parliament')
  })

  it('duplicate query updates timestamp to most recent submission', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('parliament'))
    const firstTimestamp = result.current.entries[0].timestamp
    act(() => result.current.recordSearch('parliament'))
    const secondTimestamp = result.current.entries[0].timestamp
    expect(secondTimestamp).toBeGreaterThanOrEqual(firstTimestamp)
  })

  it('duplicate query moves entry to front of list', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('first'))
    act(() => result.current.recordSearch('second'))
    act(() => result.current.recordSearch('first')) // re-submit first
    expect(result.current.entries[0].query).toBe('first')
    expect(result.current.entries[1].query).toBe('second')
  })

  it('FIFO rotation: 11th distinct entry removes oldest, list stays at 10', () => {
    const { result } = renderHook(() => useCookieHistory())
    for (let i = 1; i <= 10; i++) {
      act(() => result.current.recordSearch(`query-${i}`))
    }
    expect(result.current.entries).toHaveLength(10)
    expect(result.current.entries[9].query).toBe('query-1') // oldest is last

    act(() => result.current.recordSearch('query-11'))
    expect(result.current.entries).toHaveLength(10)
    // oldest (query-1) must not reappear
    expect(result.current.entries.find((e) => e.query === 'query-1')).toBeUndefined()
    expect(result.current.entries[0].query).toBe('query-11')
  })

  it('does nothing when query is falsy', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch(''))
    expect(result.current.entries).toHaveLength(0)
  })

  it('persists entries to localStorage', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('test query'))
    expect(stored('ss_recent')[0].query).toBe('test query')
  })

  it('stores a 500-character query at full length without truncation', () => {
    const longQuery = 'a'.repeat(500)
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch(longQuery))
    expect(result.current.entries[0].query).toBe(longQuery)
    expect(result.current.entries[0].query.length).toBe(500)
  })
})

describe('useCookieHistory — deleteEntry', () => {
  it('removes the matching entry', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('alpha'))
    act(() => result.current.recordSearch('beta'))
    act(() => result.current.deleteEntry('alpha'))
    expect(result.current.entries.find((e) => e.query === 'alpha')).toBeUndefined()
    expect(result.current.entries.find((e) => e.query === 'beta')).toBeDefined()
  })
})

describe('useCookieHistory — clearAll', () => {
  it('empties the entries list', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('alpha'))
    act(() => result.current.recordSearch('beta'))
    act(() => result.current.clearAll())
    expect(result.current.entries).toHaveLength(0)
    expect(stored('ss_recent')).toEqual([])
  })
})

describe('useCookieHistory — storageEnabled', () => {
  it('returns storageEnabled: true when localStorage works', () => {
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.storageEnabled).toBe(true)
  })

  it('returns storageEnabled: false and empty entries when storage is blocked', () => {
    window.localStorage.setItem('ss_recent', JSON.stringify([{ query: 'x', timestamp: Date.now() }]))
    disableStorage()
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.storageEnabled).toBe(false)
    expect(result.current.entries).toHaveLength(0)
  })

  it('does not throw or record when storage is blocked', () => {
    disableStorage()
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('something'))
    expect(result.current.entries).toHaveLength(0)
  })
})

describe('useCookieHistory — init from storage', () => {
  it('loads pre-existing entries on mount', () => {
    const now = Date.now()
    const existing = [
      { query: 'newest query', timestamp: now },
      { query: 'older query', timestamp: now - 1000 },
    ]
    window.localStorage.setItem('ss_recent', JSON.stringify(existing))
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.entries).toEqual(existing)
  })

  it('returns empty array if stored value is not an array', () => {
    window.localStorage.setItem('ss_recent', JSON.stringify({ invalid: 'shape' }))
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.entries).toEqual([])
  })

  it('drops entries older than 30 days', () => {
    const now = Date.now()
    window.localStorage.setItem(
      'ss_recent',
      JSON.stringify([
        { query: 'fresh', timestamp: now - 1000 },
        { query: 'stale', timestamp: now - 31 * 24 * 60 * 60 * 1000 },
      ])
    )
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.entries.map((e) => e.query)).toEqual(['fresh'])
  })

  it('migrates the legacy ss_recent cookie once', () => {
    const legacy = [{ query: 'from cookie', timestamp: Date.now() }]
    Cookies.set('ss_recent', JSON.stringify(legacy))
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.entries).toEqual(legacy)
    expect(stored('ss_recent')).toEqual(legacy)
    expect(Cookies.get('ss_recent')).toBeUndefined()
  })
})
