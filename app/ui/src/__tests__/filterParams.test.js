import { describe, it, expect } from 'vitest'
import {
  buildSearchUrl,
  filtersFromSearchParams,
  setFilterSearchParams,
} from '../lib/filterParams.js'
import { defaultFilterState } from '../lib/filterState.js'

function filters(overrides = {}) {
  return { ...defaultFilterState(), ...overrides }
}

describe('filterParams', () => {
  it('writes no filter params for the default filter state', () => {
    const params = setFilterSearchParams(new URLSearchParams('q=x'), defaultFilterState())
    expect(params.toString()).toBe('q=x')
  })

  it('round-trips every non-default filter through the URL', () => {
    const state = filters({
      sources: ['LS', 'RS'],
      proceeding_types: ['debate', 'zero_hour'],
      date_from: '2020-01-01',
      date_to: '2024-12-31',
      speaker: 'Sushma Swaraj',
      session: 'Budget Session 2023',
      subject: 'Health & family',
    })
    const params = setFilterSearchParams(new URLSearchParams(), state)
    expect(params.get('source')).toBe('LS,RS')
    expect(params.get('type')).toBe('debate,zero_hour')
    expect(params.get('from')).toBe('2020-01-01')
    // Survives serialization to a string and back.
    expect(filtersFromSearchParams(new URLSearchParams(params.toString()))).toEqual(state)
  })

  it('replaces filter params already present', () => {
    const params = new URLSearchParams('q=x&source=CA&speaker=old&debug=1')
    setFilterSearchParams(params, filters({ sources: ['RS'] }))
    expect(params.get('source')).toBe('RS')
    expect(params.get('speaker')).toBeNull()
    expect(params.get('debug')).toBe('1')
  })

  it('reads the default state from a URL without filter params', () => {
    expect(filtersFromSearchParams(new URLSearchParams('q=x'))).toEqual(defaultFilterState())
  })

  it('drops unknown or malformed values from a hand-edited URL', () => {
    const f = filtersFromSearchParams(
      new URLSearchParams('source=LS,XX&type=bogus&from=2020&to=2024-01-01&speaker=%20%20')
    )
    expect(f.sources).toEqual(['LS'])
    expect(f.proceeding_types).toEqual(defaultFilterState().proceeding_types)
    expect(f.date_from).toBeNull()
    expect(f.date_to).toBe('2024-01-01')
    expect(f.speaker).toBeNull()
  })

  it('buildSearchUrl includes query, page, non-default sort and filters', () => {
    const url = buildSearchUrl({
      query: 'water rights',
      filters: filters({ sources: ['CA'] }),
      sort: 'chronological',
    })
    const params = new URLSearchParams(url.split('?')[1])
    expect(url.startsWith('/search?')).toBe(true)
    expect(params.get('q')).toBe('water rights')
    expect(params.get('page')).toBe('1')
    expect(params.get('sort')).toBe('chronological')
    expect(params.get('source')).toBe('CA')
  })

  it('buildSearchUrl omits default sort and default filters', () => {
    expect(buildSearchUrl({ query: 'x', filters: null, sort: 'relevance' })).toBe(
      '/search?q=x&page=1'
    )
  })
})
