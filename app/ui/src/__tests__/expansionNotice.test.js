import { describe, it, expect } from 'vitest'
import {
  parseExpansionNotice,
  formatExpansionNotice,
  hasExpansion,
} from '../lib/expansionNotice.js'

describe('parseExpansionNotice', () => {
  it('returns [] for non-array input', () => {
    expect(parseExpansionNotice(null)).toEqual([])
    expect(parseExpansionNotice(undefined)).toEqual([])
    expect(parseExpansionNotice('term')).toEqual([])
  })

  it('strips whitespace and empties', () => {
    expect(parseExpansionNotice(['  PM  ', '', 'CM'])).toEqual(['PM', 'CM'])
  })
})

describe('formatExpansionNotice', () => {
  it('returns empty string when no expansion', () => {
    expect(formatExpansionNotice([])).toBe('')
    expect(formatExpansionNotice(null)).toBe('')
  })

  it('formats as "Also searching for: a, b"', () => {
    expect(formatExpansionNotice(['Prime Minister', 'Chief Minister'])).toBe(
      'Also searching for: Prime Minister, Chief Minister'
    )
  })
})

describe('hasExpansion', () => {
  it('false for empty / invalid', () => {
    expect(hasExpansion([])).toBe(false)
    expect(hasExpansion(null)).toBe(false)
  })

  it('true when at least one valid term', () => {
    expect(hasExpansion(['PM'])).toBe(true)
  })
})
