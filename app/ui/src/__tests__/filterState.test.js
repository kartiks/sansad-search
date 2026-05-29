import { describe, it, expect } from 'vitest'
import {
  defaultFilterState,
  isDefaultFilterState,
  validateFilterState,
  isFilterStateValid,
  toApiFilters,
} from '../lib/filterState.js'

describe('defaultFilterState', () => {
  it('defaults to all sources checked', () => {
    const s = defaultFilterState()
    expect([...s.sources].sort()).toEqual(['CA', 'LS', 'RS'])
  })

  it('defaults to all proceeding types checked', () => {
    const s = defaultFilterState()
    expect(s.proceeding_types).toHaveLength(9)
  })

  it('defaults date / speaker / session to null', () => {
    const s = defaultFilterState()
    expect(s.date_from).toBeNull()
    expect(s.date_to).toBeNull()
    expect(s.speaker).toBeNull()
    expect(s.session).toBeNull()
  })

  it('returns a fresh object each call (no shared mutation)', () => {
    const a = defaultFilterState()
    a.sources.push('XX')
    const b = defaultFilterState()
    expect(b.sources).not.toContain('XX')
  })
})

describe('isDefaultFilterState', () => {
  it('detects the default filter state', () => {
    expect(isDefaultFilterState(defaultFilterState())).toBe(true)
  })

  it('detects a non-default filter state', () => {
    const s = defaultFilterState()
    s.sources = ['LS']
    expect(isDefaultFilterState(s)).toBe(false)
  })

  it('null / undefined is treated as default', () => {
    expect(isDefaultFilterState(null)).toBe(true)
    expect(isDefaultFilterState(undefined)).toBe(true)
  })
})

describe('validateFilterState', () => {
  it('returns no errors for default state', () => {
    expect(validateFilterState(defaultFilterState())).toEqual({})
  })

  it('flags empty sources', () => {
    const s = defaultFilterState()
    s.sources = []
    const errors = validateFilterState(s)
    expect(errors.sources).toBe('Select at least one source')
  })

  it('flags empty proceeding types', () => {
    const s = defaultFilterState()
    s.proceeding_types = []
    const errors = validateFilterState(s)
    expect(errors.proceeding_types).toBe('Select at least one proceeding type')
  })

  it('flags From > To', () => {
    const s = defaultFilterState()
    s.date_from = '2024-12-01'
    s.date_to = '2024-01-01'
    const errors = validateFilterState(s)
    expect(errors.date_range).toBe('From date must be before To date')
  })

  it('does not flag From == To', () => {
    const s = defaultFilterState()
    s.date_from = '2024-01-01'
    s.date_to = '2024-01-01'
    const errors = validateFilterState(s)
    expect(errors.date_range).toBeUndefined()
  })

  it('isFilterStateValid is true for default state', () => {
    expect(isFilterStateValid(defaultFilterState())).toBe(true)
  })

  it('isFilterStateValid is false when any error exists', () => {
    const s = defaultFilterState()
    s.sources = []
    expect(isFilterStateValid(s)).toBe(false)
  })
})

describe('toApiFilters', () => {
  it('returns null for default filter state', () => {
    expect(toApiFilters(defaultFilterState())).toBeNull()
  })

  it('returns null for null/undefined input', () => {
    expect(toApiFilters(null)).toBeNull()
    expect(toApiFilters(undefined)).toBeNull()
  })

  it('omits keys whose value is the default', () => {
    const s = defaultFilterState()
    s.date_from = '2024-01-01'
    const result = toApiFilters(s)
    expect(result).toEqual({ date_from: '2024-01-01' })
    expect(result.sources).toBeUndefined()
    expect(result.proceeding_types).toBeUndefined()
  })

  it('includes a single source when narrowed', () => {
    const s = defaultFilterState()
    s.sources = ['LS']
    expect(toApiFilters(s)).toMatchObject({ sources: ['LS'] })
  })

  it('trims speaker and session inputs', () => {
    const s = defaultFilterState()
    s.speaker = '  Singh  '
    s.session = ''
    const result = toApiFilters(s)
    expect(result.speaker).toBe('Singh')
    expect(result.session).toBeUndefined()
  })
})
