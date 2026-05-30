import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Mock the cookie module so tests control storage without real cookies
vi.mock('../lib/cookie.js', () => ({
  areCookiesEnabled: vi.fn().mockReturnValue(true),
  readCookie: vi.fn().mockReturnValue(null),
  writeCookie: vi.fn(),
  deleteCookie: vi.fn(),
  trimRecentToFit: vi.fn((entries) => entries),
  RECENT_COOKIE: 'ss_recent',
  SAVED_COOKIE: 'ss_saved',
  MAX_COMBINED_BYTES: 4096,
}))

import { useCookieHistory } from '../hooks/useCookieHistory.js'
import * as cookieModule from '../lib/cookie.js'

beforeEach(() => {
  vi.clearAllMocks()
  cookieModule.areCookiesEnabled.mockReturnValue(true)
  cookieModule.readCookie.mockReturnValue(null)
  cookieModule.trimRecentToFit.mockImplementation((entries) => entries)
})

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

  it('calls writeCookie with updated entries', () => {
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('test query'))
    expect(cookieModule.writeCookie).toHaveBeenCalled()
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
    expect(cookieModule.deleteCookie).toHaveBeenCalled()
  })
})

describe('useCookieHistory — cookiesEnabled', () => {
  it('returns cookiesEnabled: true when areCookiesEnabled returns true', () => {
    cookieModule.areCookiesEnabled.mockReturnValue(true)
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.cookiesEnabled).toBe(true)
  })

  it('returns cookiesEnabled: false and empty entries when cookies disabled', () => {
    cookieModule.areCookiesEnabled.mockReturnValue(false)
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.cookiesEnabled).toBe(false)
    expect(result.current.entries).toHaveLength(0)
  })

  it('does not write when cookies are disabled', () => {
    cookieModule.areCookiesEnabled.mockReturnValue(false)
    const { result } = renderHook(() => useCookieHistory())
    act(() => result.current.recordSearch('something'))
    expect(cookieModule.writeCookie).not.toHaveBeenCalled()
  })
})

describe('useCookieHistory — init from cookie', () => {
  it('loads pre-existing entries from cookie on mount', () => {
    const existing = [
      { query: 'older query', timestamp: 100 },
      { query: 'newest query', timestamp: 200 },
    ]
    cookieModule.readCookie.mockReturnValue(existing)
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.entries).toEqual(existing)
  })

  it('returns empty array if cookie value is not an array', () => {
    cookieModule.readCookie.mockReturnValue({ invalid: 'shape' })
    const { result } = renderHook(() => useCookieHistory())
    expect(result.current.entries).toEqual([])
  })
})
