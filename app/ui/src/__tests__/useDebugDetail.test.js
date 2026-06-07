import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useDebugDetail, DEBUG_PROCESSED_ENDPOINT, DEBUG_RAW_ENDPOINT } from '../hooks/useDebugDetail.js'

const MOCK_ID = 'test-id-123'
const PROCESSED_URL = DEBUG_PROCESSED_ENDPOINT(MOCK_ID)
const RAW_URL = DEBUG_RAW_ENDPOINT(MOCK_ID)

function mockFetch(handlers) {
  global.fetch = vi.fn((url) => {
    const handler = handlers[url]
    if (handler) return handler()
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
  })
}

beforeEach(() => { vi.clearAllMocks() })
afterEach(() => { delete global.fetch })

// ── Endpoint construction ─────────────────────────────────────────────────────

describe('DEBUG_PROCESSED_ENDPOINT', () => {
  it('builds the correct URL for a given id', () => {
    expect(DEBUG_PROCESSED_ENDPOINT('abc')).toBe('/api/debug/processed/abc')
  })

  it('URL-encodes special characters in the id', () => {
    expect(DEBUG_PROCESSED_ENDPOINT('a b')).toContain(encodeURIComponent('a b'))
  })
})

describe('DEBUG_RAW_ENDPOINT', () => {
  it('builds the correct URL for a given id', () => {
    expect(DEBUG_RAW_ENDPOINT('abc')).toBe('/api/debug/raw/abc')
  })
})

// ── Initial state ─────────────────────────────────────────────────────────────

describe('useDebugDetail — initial state', () => {
  it('starts with no data and no errors', () => {
    const { result } = renderHook(() => useDebugDetail(MOCK_ID))
    expect(result.current.processedData).toBeNull()
    expect(result.current.processedError).toBeNull()
    expect(result.current.processedLoading).toBe(false)
    expect(result.current.processedFetched).toBe(false)
    expect(result.current.rawData).toBeNull()
    expect(result.current.rawError).toBeNull()
    expect(result.current.rawLoading).toBe(false)
    expect(result.current.rawFetched).toBe(false)
  })

  it('does not call fetch on mount', () => {
    global.fetch = vi.fn()
    renderHook(() => useDebugDetail(MOCK_ID))
    expect(global.fetch).not.toHaveBeenCalled()
  })
})

// ── fetchProcessed ────────────────────────────────────────────────────────────

describe('useDebugDetail — fetchProcessed', () => {
  it('fetches /api/debug/processed/{id} on first call', async () => {
    const processedPayload = { table: 'speeches', row: { id: MOCK_ID } }
    mockFetch({
      [PROCESSED_URL]: () => Promise.resolve({
        ok: true, status: 200,
        json: async () => processedPayload,
      }),
    })

    const { result } = renderHook(() => useDebugDetail(MOCK_ID))
    await act(async () => { result.current.fetchProcessed() })
    await waitFor(() => expect(result.current.processedFetched).toBe(true))

    expect(result.current.processedData).toEqual(processedPayload)
    expect(result.current.processedError).toBeNull()
    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(global.fetch).toHaveBeenCalledWith(PROCESSED_URL)
  })

  it('second call is a no-op — does not fetch again', async () => {
    const processedPayload = { table: 'speeches', row: { id: MOCK_ID } }
    mockFetch({
      [PROCESSED_URL]: () => Promise.resolve({
        ok: true, status: 200,
        json: async () => processedPayload,
      }),
    })

    const { result } = renderHook(() => useDebugDetail(MOCK_ID))
    await act(async () => { result.current.fetchProcessed() })
    await waitFor(() => expect(result.current.processedFetched).toBe(true))
    expect(global.fetch).toHaveBeenCalledTimes(1)

    // Second call
    await act(async () => { result.current.fetchProcessed() })
    expect(global.fetch).toHaveBeenCalledTimes(1)  // still only 1
  })

  it('sets processedError on 404', async () => {
    mockFetch({
      [PROCESSED_URL]: () => Promise.resolve({
        ok: false, status: 404,
        json: async () => ({ error: 'not_found', message: 'Record not found.' }),
      }),
    })

    const { result } = renderHook(() => useDebugDetail(MOCK_ID))
    await act(async () => { result.current.fetchProcessed() })
    await waitFor(() => expect(result.current.processedFetched).toBe(true))

    expect(result.current.processedData).toBeNull()
    expect(result.current.processedError).not.toBeNull()
    expect(result.current.processedError.status).toBe(404)
  })
})

// ── fetchRaw ──────────────────────────────────────────────────────────────────

describe('useDebugDetail — fetchRaw', () => {
  it('fetches /api/debug/raw/{id} on first call', async () => {
    const rawPayload = { row: { canonical_doc_id: 'abc', corpus: 'LS' } }
    mockFetch({
      [RAW_URL]: () => Promise.resolve({
        ok: true, status: 200,
        json: async () => rawPayload,
      }),
    })

    const { result } = renderHook(() => useDebugDetail(MOCK_ID))
    await act(async () => { result.current.fetchRaw() })
    await waitFor(() => expect(result.current.rawFetched).toBe(true))

    expect(result.current.rawData).toEqual(rawPayload)
    expect(result.current.rawError).toBeNull()
    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(global.fetch).toHaveBeenCalledWith(RAW_URL)
  })

  it('second call is a no-op — does not fetch again', async () => {
    mockFetch({
      [RAW_URL]: () => Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ row: {} }),
      }),
    })

    const { result } = renderHook(() => useDebugDetail(MOCK_ID))
    await act(async () => { result.current.fetchRaw() })
    await waitFor(() => expect(result.current.rawFetched).toBe(true))
    expect(global.fetch).toHaveBeenCalledTimes(1)

    await act(async () => { result.current.fetchRaw() })
    expect(global.fetch).toHaveBeenCalledTimes(1)
  })

  it('sets rawError on 404', async () => {
    mockFetch({
      [RAW_URL]: () => Promise.resolve({
        ok: false, status: 404,
        json: async () => ({ error: 'not_found', message: 'Raw document not available.' }),
      }),
    })

    const { result } = renderHook(() => useDebugDetail(MOCK_ID))
    await act(async () => { result.current.fetchRaw() })
    await waitFor(() => expect(result.current.rawFetched).toBe(true))

    expect(result.current.rawData).toBeNull()
    expect(result.current.rawError).not.toBeNull()
    expect(result.current.rawError.status).toBe(404)
  })
})

// ── Section independence ──────────────────────────────────────────────────────

describe('useDebugDetail — section independence', () => {
  it('fetchProcessed does not trigger a raw fetch', async () => {
    mockFetch({
      [PROCESSED_URL]: () => Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ table: 'speeches', row: {} }),
      }),
    })

    const { result } = renderHook(() => useDebugDetail(MOCK_ID))
    await act(async () => { result.current.fetchProcessed() })
    await waitFor(() => expect(result.current.processedFetched).toBe(true))

    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(global.fetch).toHaveBeenCalledWith(PROCESSED_URL)
    expect(global.fetch).not.toHaveBeenCalledWith(RAW_URL)
    expect(result.current.rawFetched).toBe(false)
  })

  it('fetchRaw does not trigger a processed fetch', async () => {
    mockFetch({
      [RAW_URL]: () => Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ row: {} }),
      }),
    })

    const { result } = renderHook(() => useDebugDetail(MOCK_ID))
    await act(async () => { result.current.fetchRaw() })
    await waitFor(() => expect(result.current.rawFetched).toBe(true))

    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(global.fetch).toHaveBeenCalledWith(RAW_URL)
    expect(global.fetch).not.toHaveBeenCalledWith(PROCESSED_URL)
    expect(result.current.processedFetched).toBe(false)
  })

  it('raw sections for different result ids cache separately', async () => {
    const RAW_URL_B = DEBUG_RAW_ENDPOINT('other-id')
    mockFetch({
      [RAW_URL]: () => Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ row: { id: MOCK_ID } }),
      }),
      [RAW_URL_B]: () => Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ row: { id: 'other-id' } }),
      }),
    })

    const { result: resultA } = renderHook(() => useDebugDetail(MOCK_ID))
    const { result: resultB } = renderHook(() => useDebugDetail('other-id'))

    await act(async () => {
      resultA.current.fetchRaw()
      resultB.current.fetchRaw()
    })
    await waitFor(() =>
      expect(resultA.current.rawFetched).toBe(true) &&
      expect(resultB.current.rawFetched).toBe(true)
    )

    // Two separate calls — one per result id
    expect(global.fetch).toHaveBeenCalledTimes(2)
  })
})
