import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { fetchRecord, useRecord } from '../hooks/useRecord.js'

// ── fetchRecord unit tests ────────────────────────────────────────────────────

describe('fetchRecord', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns parsed JSON on 200', async () => {
    const data = { id: 'abc', record_type: 'speech' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => data,
    }))
    const result = await fetchRecord('abc')
    expect(result).toEqual(data)
    vi.unstubAllGlobals()
  })

  it('throws error with status=404 on 404 response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: 'not_found', message: 'Record not found.' }),
    }))
    await expect(fetchRecord('nonexistent')).rejects.toMatchObject({ status: 404 })
    vi.unstubAllGlobals()
  })

  it('throws error with http_500 message on 500 response with no body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => { throw new Error('no json') },
    }))
    await expect(fetchRecord('id')).rejects.toMatchObject({ message: 'http_500' })
    vi.unstubAllGlobals()
  })

  it('throws network_error when fetch throws', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network failure')))
    await expect(fetchRecord('id')).rejects.toMatchObject({ message: 'network_error' })
    vi.unstubAllGlobals()
  })

  it('rethrows AbortError without wrapping', async () => {
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError))
    await expect(fetchRecord('id')).rejects.toMatchObject({ name: 'AbortError' })
    vi.unstubAllGlobals()
  })
})

// ── useRecord hook tests ──────────────────────────────────────────────────────

describe('useRecord', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('starts in loading state when id provided', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'abc' }),
    }))
    const { result } = renderHook(() => useRecord('abc'))
    expect(result.current.loading).toBe(true)
    expect(result.current.data).toBeNull()
  })

  it('resolves data on successful fetch', async () => {
    const record = { id: 'abc', record_type: 'speech', adjacent: { prev_id: null, next_id: null } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => record,
    }))
    const { result } = renderHook(() => useRecord('abc'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(record)
    expect(result.current.error).toBeNull()
    expect(result.current.notFound).toBe(false)
  })

  it('sets notFound=true (not error) on 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: 'not_found', message: 'Record not found.' }),
    }))
    const { result } = renderHook(() => useRecord('nonexistent'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.notFound).toBe(true)
    expect(result.current.error).toBeNull()
    expect(result.current.data).toBeNull()
  })

  it('sets error (not notFound) on 500', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => null,
    }))
    const { result } = renderHook(() => useRecord('id'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).not.toBeNull()
    expect(result.current.notFound).toBe(false)
  })

  it('does nothing when id is falsy', () => {
    vi.stubGlobal('fetch', vi.fn())
    const { result } = renderHook(() => useRecord(null))
    expect(result.current.loading).toBe(false)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('retry increments reloadToken and re-fetches', async () => {
    let callCount = 0
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => {
      callCount++
      return {
        ok: true,
        status: 200,
        json: async () => ({ id: 'abc', callCount }),
      }
    }))
    const { result } = renderHook(() => useRecord('abc'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(callCount).toBe(1)

    result.current.retry()
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(callCount).toBe(2)
  })
})
