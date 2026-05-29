import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  buildSearchRequestBody,
  postSearch,
  SEARCH_ENDPOINT,
} from '../hooks/useSearch.js'
import { defaultFilterState } from '../lib/filterState.js'

beforeEach(() => {
  global.fetch = vi.fn()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('buildSearchRequestBody', () => {
  it('omits filters when state is default', () => {
    const body = buildSearchRequestBody({
      query: 'rights',
      filters: defaultFilterState(),
      sort: 'relevance',
      page: 1,
    })
    expect(body.filters).toBeUndefined()
  })

  it('includes filters when state diverges from defaults', () => {
    const filters = defaultFilterState()
    filters.sources = ['LS']
    filters.date_from = '2020-01-01'
    const body = buildSearchRequestBody({
      query: 'rights',
      filters,
      sort: 'relevance',
      page: 1,
    })
    expect(body.filters).toEqual({ sources: ['LS'], date_from: '2020-01-01' })
  })

  it('clamps page to >= 1', () => {
    const body = buildSearchRequestBody({
      query: 'a',
      filters: null,
      sort: 'relevance',
      page: 0,
    })
    expect(body.page).toBe(1)
    const body2 = buildSearchRequestBody({
      query: 'a',
      filters: null,
      sort: 'relevance',
      page: -5,
    })
    expect(body2.page).toBe(1)
  })

  it('defaults sort to relevance', () => {
    const body = buildSearchRequestBody({ query: 'a', filters: null, sort: '', page: 1 })
    expect(body.sort).toBe('relevance')
  })
})

describe('postSearch', () => {
  it('POSTs JSON to /api/search and returns parsed payload', async () => {
    const payload = { total: 1, results: [] }
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload,
    })
    const result = await postSearch({
      query: 'rights',
      filters: defaultFilterState(),
      sort: 'relevance',
      page: 1,
    })
    expect(result).toEqual(payload)
    expect(global.fetch).toHaveBeenCalledWith(
      SEARCH_ENDPOINT,
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    )
  })

  it('throws with status when response not OK', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        error: 'validation_error',
        code: 'query_too_short',
        message: 'Query must contain at least 2 characters.',
      }),
    })
    await expect(
      postSearch({ query: 'a', filters: null, sort: 'relevance', page: 1 })
    ).rejects.toMatchObject({ status: 400 })
  })

  it('throws network_error on fetch failure', async () => {
    global.fetch.mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(
      postSearch({ query: 'rights', filters: null, sort: 'relevance', page: 1 })
    ).rejects.toThrow('network_error')
  })

  it('serialises filters into the body', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ total: 0, results: [] }),
    })
    const filters = defaultFilterState()
    filters.sources = ['RS']
    await postSearch({ query: 'q', filters, sort: 'chronological', page: 2 })
    const args = global.fetch.mock.calls[0][1]
    const body = JSON.parse(args.body)
    expect(body).toEqual({
      query: 'q',
      sort: 'chronological',
      page: 2,
      filters: { sources: ['RS'] },
    })
  })
})
