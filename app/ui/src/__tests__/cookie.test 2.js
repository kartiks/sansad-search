import { describe, it, expect, beforeEach } from 'vitest'
import Cookies from 'js-cookie'
import {
  RECENT_COOKIE,
  SAVED_COOKIE,
  MAX_COMBINED_BYTES,
  areCookiesEnabled,
  readCookie,
  writeCookie,
  deleteCookie,
  trimRecentToFit,
} from '../lib/cookie.js'

function clearAllCookies() {
  Object.keys(Cookies.get()).forEach((name) => Cookies.remove(name))
}

beforeEach(() => {
  clearAllCookies()
})

describe('areCookiesEnabled', () => {
  it('returns true in jsdom environment', () => {
    expect(areCookiesEnabled()).toBe(true)
  })

  it('leaves no test cookie behind', () => {
    areCookiesEnabled()
    expect(Cookies.get('__cc__')).toBeUndefined()
  })
})

describe('readCookie / writeCookie / deleteCookie', () => {
  it('returns null for a non-existent cookie', () => {
    expect(readCookie('nonexistent')).toBeNull()
  })

  it('reads back data written by writeCookie', () => {
    const data = [{ query: 'hello', timestamp: 1000 }]
    writeCookie(RECENT_COOKIE, data)
    expect(readCookie(RECENT_COOKIE)).toEqual(data)
  })

  it('handles non-JSON cookie value gracefully', () => {
    Cookies.set(RECENT_COOKIE, 'not-json')
    expect(readCookie(RECENT_COOKIE)).toBeNull()
  })

  it('deleteCookie removes the cookie', () => {
    writeCookie(RECENT_COOKIE, [1, 2, 3])
    deleteCookie(RECENT_COOKIE)
    expect(readCookie(RECENT_COOKIE)).toBeNull()
  })

  it('writeCookie passes options to js-cookie', () => {
    writeCookie(RECENT_COOKIE, ['a'], { expires: 30 })
    expect(readCookie(RECENT_COOKIE)).toEqual(['a'])
  })
})

describe('trimRecentToFit', () => {
  it('returns entries unchanged when combined size is within limit', () => {
    const recent = [{ query: 'hello', timestamp: 1 }]
    const saved = []
    const result = trimRecentToFit(recent, saved)
    expect(result).toEqual(recent)
  })

  it('removes oldest entries (last in array) when over limit', () => {
    // Each entry with a 2000-char query serializes to ~2030 bytes.
    // Two such entries in recent = ~4064 bytes, which exceeds MAX_COMBINED_BYTES
    // when combined with even a tiny saved array. After trimming the oldest
    // (second) entry, combined drops well below the limit.
    const bigQuery = 'x'.repeat(2000)
    const recent = [
      { query: `${bigQuery}-newest`, timestamp: 1 },
      { query: `${bigQuery}-oldest`, timestamp: 0 },
    ]
    const saved = [{ id: 'a', name: 'b', query: 'c', filters: {}, timestamp: 0 }]
    const result = trimRecentToFit(recent, saved)
    // Oldest entry (index 1) should have been removed
    expect(result.length).toBeLessThan(recent.length)
    // Newest entry (index 0) must be preserved
    expect(result[0]).toEqual(recent[0])
  })

  it('returns empty array if all entries must be trimmed', () => {
    // Saved alone is already at the limit
    const saved = [{ data: 'x'.repeat(MAX_COMBINED_BYTES) }]
    const recent = [{ query: 'hello', timestamp: 1 }]
    const result = trimRecentToFit(recent, saved)
    expect(result).toEqual([])
  })

  it('handles null savedEntries', () => {
    const recent = [{ query: 'test', timestamp: 1 }]
    const result = trimRecentToFit(recent, null)
    expect(result).toEqual(recent)
  })
})
