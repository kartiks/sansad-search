import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import Cookies from 'js-cookie'
import {
  RECENT_KEY,
  SAVED_KEY,
  isStorageAvailable,
  readList,
  writeList,
} from '../lib/searchStorage.js'

beforeEach(() => {
  window.localStorage.clear()
  Object.keys(Cookies.get()).forEach((name) => Cookies.remove(name))
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('searchStorage', () => {
  it('reports storage as available in jsdom', () => {
    expect(isStorageAvailable()).toBe(true)
    expect(window.localStorage.getItem('__ss_test__')).toBeNull()
  })

  it('round-trips a list', () => {
    expect(writeList(RECENT_KEY, [{ query: 'a', timestamp: 1 }])).toBe(true)
    expect(readList(RECENT_KEY)).toEqual([{ query: 'a', timestamp: 1 }])
  })

  it('returns [] for corrupt or non-array data', () => {
    window.localStorage.setItem(RECENT_KEY, 'not-json')
    expect(readList(RECENT_KEY)).toEqual([])
    window.localStorage.setItem(RECENT_KEY, '{"a":1}')
    expect(readList(RECENT_KEY)).toEqual([])
  })

  it('stores far more than the old 4 KB cookie limit', () => {
    const entries = Array.from({ length: 20 }, (_, i) => ({
      id: `id-${i}`,
      name: 'n'.repeat(60),
      query: 'q'.repeat(500),
      filters: { speaker: 's'.repeat(100) },
      timestamp: i,
    }))
    writeList(SAVED_KEY, entries)
    expect(readList(SAVED_KEY)).toHaveLength(20)
  })

  it('reports unavailable and never throws when storage throws', () => {
    vi.spyOn(Object.getPrototypeOf(window.localStorage), 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    vi.spyOn(Object.getPrototypeOf(window.localStorage), 'getItem').mockImplementation(() => {
      throw new Error('SecurityError')
    })
    expect(isStorageAvailable()).toBe(false)
    expect(writeList(RECENT_KEY, [])).toBe(false)
    expect(readList(RECENT_KEY)).toEqual([])
  })
})

describe('searchStorage — one-time cookie migration', () => {
  it('copies the legacy cookie into localStorage and deletes the cookie', () => {
    const saved = [{ id: 'x', name: 'n', query: 'q', filters: {}, timestamp: 1 }]
    Cookies.set('ss_saved', JSON.stringify(saved))
    expect(readList(SAVED_KEY)).toEqual(saved)
    expect(JSON.parse(window.localStorage.getItem(SAVED_KEY))).toEqual(saved)
    expect(Cookies.get('ss_saved')).toBeUndefined()
  })

  it('ignores the cookie once localStorage has the key', () => {
    window.localStorage.setItem(RECENT_KEY, '[]')
    Cookies.set('ss_recent', JSON.stringify([{ query: 'old', timestamp: 1 }]))
    expect(readList(RECENT_KEY)).toEqual([])
  })

  it('keeps the cookie if the localStorage write fails', () => {
    Cookies.set('ss_recent', JSON.stringify([{ query: 'old', timestamp: 1 }]))
    vi.spyOn(Object.getPrototypeOf(window.localStorage), 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(readList(RECENT_KEY)).toEqual([{ query: 'old', timestamp: 1 }])
    expect(Cookies.get('ss_recent')).toBeDefined()
  })

  it('returns [] when there is neither stored data nor a cookie', () => {
    expect(readList(RECENT_KEY)).toEqual([])
  })
})
