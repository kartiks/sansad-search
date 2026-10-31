import { describe, it, expect, beforeEach } from 'vitest'
import Cookies from 'js-cookie'
import { RECENT_COOKIE, readCookie, deleteCookie } from '../lib/cookie.js'

// lib/cookie.js now only reads and removes the legacy cookies for the
// one-time migration to localStorage (see searchStorage.test.js).

function clearAllCookies() {
  Object.keys(Cookies.get()).forEach((name) => Cookies.remove(name))
}

beforeEach(() => {
  clearAllCookies()
})

describe('readCookie / deleteCookie', () => {
  it('returns null for a non-existent cookie', () => {
    expect(readCookie('nonexistent')).toBeNull()
  })

  it('parses a JSON cookie value', () => {
    const data = [{ query: 'hello', timestamp: 1000 }]
    Cookies.set(RECENT_COOKIE, JSON.stringify(data))
    expect(readCookie(RECENT_COOKIE)).toEqual(data)
  })

  it('handles non-JSON cookie value gracefully', () => {
    Cookies.set(RECENT_COOKIE, 'not-json')
    expect(readCookie(RECENT_COOKIE)).toBeNull()
  })

  it('deleteCookie removes the cookie', () => {
    Cookies.set(RECENT_COOKIE, '[1,2,3]')
    deleteCookie(RECENT_COOKIE)
    expect(readCookie(RECENT_COOKIE)).toBeNull()
  })
})
