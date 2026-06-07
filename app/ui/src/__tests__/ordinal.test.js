import { describe, it, expect } from 'vitest'
import { toOrdinal } from '../lib/ordinal.js'

describe('toOrdinal', () => {
  it('1 → "1st"', () => expect(toOrdinal(1)).toBe('1st'))
  it('2 → "2nd"', () => expect(toOrdinal(2)).toBe('2nd'))
  it('3 → "3rd"', () => expect(toOrdinal(3)).toBe('3rd'))
  it('4 → "4th"', () => expect(toOrdinal(4)).toBe('4th'))

  // Teens are always "th" (the standard gotcha).
  it('11 → "11th"', () => expect(toOrdinal(11)).toBe('11th'))
  it('12 → "12th"', () => expect(toOrdinal(12)).toBe('12th'))
  it('13 → "13th"', () => expect(toOrdinal(13)).toBe('13th'))

  it('17 → "17th"', () => expect(toOrdinal(17)).toBe('17th'))
  it('18 → "18th"', () => expect(toOrdinal(18)).toBe('18th'))

  it('21 → "21st"', () => expect(toOrdinal(21)).toBe('21st'))
  it('22 → "22nd"', () => expect(toOrdinal(22)).toBe('22nd'))
  it('23 → "23rd"', () => expect(toOrdinal(23)).toBe('23rd'))

  it('111 → "111th" (teen rule on hundreds)', () => expect(toOrdinal(111)).toBe('111th'))
  it('101 → "101st"', () => expect(toOrdinal(101)).toBe('101st'))

  it('returns null for null/undefined', () => {
    expect(toOrdinal(null)).toBeNull()
    expect(toOrdinal(undefined)).toBeNull()
  })

  it('returns null for non-integers', () => {
    expect(toOrdinal(1.5)).toBeNull()
    expect(toOrdinal('17')).toBeNull()
  })
})
