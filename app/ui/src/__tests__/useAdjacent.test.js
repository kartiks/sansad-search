import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { ADJACENT_ENDPOINT, fetchAdjacent, useAdjacent } from '../hooks/useAdjacent.js'
import { makeRecordDetail, makeAdjacentRecord } from './fixtures.js'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function mockAdjacentOnce(response) {
  const fn = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => response,
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

// ── ADJACENT_ENDPOINT ─────────────────────────────────────────────────────────

describe('ADJACENT_ENDPOINT', () => {
  it('builds the URL with direction, from_seq, and limit', () => {
    expect(ADJACENT_ENDPOINT('rec-1', 'next', 7)).toBe(
      '/api/record/rec-1/adjacent?direction=next&from_seq=7&limit=5'
    )
  })
})

// ── fetchAdjacent ─────────────────────────────────────────────────────────────

describe('fetchAdjacent', () => {
  it('returns parsed JSON on 200', async () => {
    const resp = { direction: 'next', records: [], has_more: false }
    mockAdjacentOnce(resp)
    const result = await fetchAdjacent('rec-1', 'next', 7)
    expect(result).toEqual(resp)
  })

  it('throws on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: 'not_found' }),
    }))
    await expect(fetchAdjacent('rec-1', 'next', 7)).rejects.toMatchObject({ status: 404 })
  })
})

// ── useAdjacent ───────────────────────────────────────────────────────────────

describe('useAdjacent', () => {
  it('initialises canLoadPrev/canLoadNext from has_prev/has_next', () => {
    const focal = makeRecordDetail({ has_prev: true, has_next: false })
    const { result } = renderHook(() => useAdjacent('speech-1', focal))
    expect(result.current.canLoadPrev).toBe(true)
    expect(result.current.canLoadNext).toBe(false)
  })

  it('loadNext appends records and updates has_more', async () => {
    const focal = makeRecordDetail({ sequence_within_sitting: 7, has_next: true })
    mockAdjacentOnce({
      direction: 'next',
      records: [
        makeAdjacentRecord({ id: 'n8', sequence_within_sitting: 8 }),
        makeAdjacentRecord({ id: 'n9', sequence_within_sitting: 9 }),
      ],
      has_more: true,
    })
    const { result } = renderHook(() => useAdjacent('speech-1', focal))

    await act(async () => {
      await result.current.loadNext()
    })

    expect(result.current.nextRecords.map((r) => r.id)).toEqual(['n8', 'n9'])
    expect(result.current.canLoadNext).toBe(true)
  })

  it('loadNext disables the control when has_more is false', async () => {
    const focal = makeRecordDetail({ sequence_within_sitting: 7, has_next: true })
    mockAdjacentOnce({
      direction: 'next',
      records: [makeAdjacentRecord({ id: 'n8', sequence_within_sitting: 8 })],
      has_more: false,
    })
    const { result } = renderHook(() => useAdjacent('speech-1', focal))

    await act(async () => {
      await result.current.loadNext()
    })

    expect(result.current.canLoadNext).toBe(false)
  })

  it('loadPrev prepends records, keeping document order', async () => {
    const focal = makeRecordDetail({ sequence_within_sitting: 10, has_prev: true })
    mockAdjacentOnce({
      direction: 'prev',
      records: [
        makeAdjacentRecord({ id: 'p7', sequence_within_sitting: 7 }),
        makeAdjacentRecord({ id: 'p8', sequence_within_sitting: 8 }),
        makeAdjacentRecord({ id: 'p9', sequence_within_sitting: 9 }),
      ],
      has_more: false,
    })
    const { result } = renderHook(() => useAdjacent('speech-1', focal))

    await act(async () => {
      await result.current.loadPrev()
    })

    expect(result.current.prevRecords.map((r) => r.id)).toEqual(['p7', 'p8', 'p9'])
  })

  it('advances from_seq across successive loadNext calls', async () => {
    const focal = makeRecordDetail({ sequence_within_sitting: 7, has_next: true })
    const calls = []
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
      calls.push(url)
      const batch = calls.length === 1
        ? { records: [makeAdjacentRecord({ id: 'n8', sequence_within_sitting: 8 })], has_more: true, direction: 'next' }
        : { records: [makeAdjacentRecord({ id: 'n9', sequence_within_sitting: 9 })], has_more: false, direction: 'next' }
      return Promise.resolve({ ok: true, status: 200, json: async () => batch })
    }))
    const { result } = renderHook(() => useAdjacent('speech-1', focal))

    await act(async () => { await result.current.loadNext() })
    await act(async () => { await result.current.loadNext() })

    // First call uses focal seq (7); second uses the highest loaded (8).
    expect(calls[0]).toContain('from_seq=7')
    expect(calls[1]).toContain('from_seq=8')
    expect(result.current.nextRecords.map((r) => r.id)).toEqual(['n8', 'n9'])
  })

  it('sets error and keeps control enabled on failed load', async () => {
    const focal = makeRecordDetail({ sequence_within_sitting: 7, has_next: true })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => null,
    }))
    const { result } = renderHook(() => useAdjacent('speech-1', focal))

    await act(async () => {
      await result.current.loadNext()
    })

    expect(result.current.errorNext).toBe(true)
    // Control returns to pre-click enabled state (re-clickable).
    expect(result.current.canLoadNext).toBe(true)
    expect(result.current.nextRecords).toEqual([])
  })
})
