import { describe, it, expect } from 'vitest'
import {
  PROCEEDING_TYPE_LABELS,
  SOURCE_LABELS,
  ALL_SOURCES,
  ALL_PROCEEDING_TYPES,
  SORT_OPTIONS,
  getProceedingTypeLabel,
  getSourceLabel,
  SEARCH_PLACEHOLDER,
  TAGLINE,
  VALIDATION_SHORT,
  ERROR_STATE_TITLE,
  ERROR_STATE_BODY,
  UNTRANSLATED_SPEECH_MESSAGE,
  SUPPLEMENTARY_PREFIX,
} from '../lib/constants.js'

describe('proceeding type labels', () => {
  it('covers every proceeding type from F05 label map', () => {
    const required = [
      ['debate', 'Debate'],
      ['starred_question', 'Starred Question'],
      ['unstarred_question', 'Unstarred Question'],
      ['zero_hour', 'Zero Hour'],
      ['short_notice_question', 'Short Notice Question'],
      ['calling_attention', 'Calling Attention'],
      ['short_duration_discussion', 'Short Duration Discussion'],
      ['adjournment_motion', 'Adjournment Motion'],
      ['private_member_bill', 'Private Member Bill'],
    ]
    for (const [key, label] of required) {
      expect(PROCEEDING_TYPE_LABELS[key]).toBe(label)
      expect(getProceedingTypeLabel(key)).toBe(label)
    }
  })

  it('returns empty string for null input', () => {
    expect(getProceedingTypeLabel(null)).toBe('')
    expect(getProceedingTypeLabel(undefined)).toBe('')
  })

  it('falls back to the raw value for an unknown type', () => {
    expect(getProceedingTypeLabel('unknown_type')).toBe('unknown_type')
  })
})

describe('source labels', () => {
  it('maps CA, LS, RS to the full body labels', () => {
    expect(SOURCE_LABELS.CA).toBe('Constituent Assembly')
    expect(SOURCE_LABELS.LS).toBe('Lok Sabha')
    expect(SOURCE_LABELS.RS).toBe('Rajya Sabha')
  })

  it('getSourceLabel returns full label or fallback', () => {
    expect(getSourceLabel('LS')).toBe('Lok Sabha')
    expect(getSourceLabel('CA')).toBe('Constituent Assembly')
    expect(getSourceLabel('RS')).toBe('Rajya Sabha')
    expect(getSourceLabel('XX')).toBe('XX')
    expect(getSourceLabel(null)).toBe('')
  })
})

describe('default arrays', () => {
  it('ALL_SOURCES contains exactly CA, LS, RS', () => {
    expect([...ALL_SOURCES].sort()).toEqual(['CA', 'LS', 'RS'])
  })

  it('ALL_PROCEEDING_TYPES contains all 9 types', () => {
    expect(ALL_PROCEEDING_TYPES).toHaveLength(9)
    expect(ALL_PROCEEDING_TYPES).toContain('debate')
    expect(ALL_PROCEEDING_TYPES).toContain('starred_question')
  })
})

describe('sort options', () => {
  it('exposes Relevance as the first/default option', () => {
    expect(SORT_OPTIONS[0]).toEqual({ value: 'relevance', label: 'Relevance' })
  })

  it('exposes Newest first and Oldest first', () => {
    const values = SORT_OPTIONS.map((o) => o.value)
    expect(values).toContain('reverse_chronological')
    expect(values).toContain('chronological')
  })
})

describe('canonical text strings', () => {
  it('matches the strings declared in the UI spec', () => {
    expect(SEARCH_PLACEHOLDER).toBe(
      'Search parliamentary debates, questions, and speeches…'
    )
    expect(TAGLINE).toBe('Search the complete record of Indian parliamentary debates.')
    expect(VALIDATION_SHORT).toBe('Enter at least 2 characters to search.')
    expect(ERROR_STATE_TITLE).toBe('Search is temporarily unavailable.')
    expect(ERROR_STATE_BODY).toBe('Please try again.')
    expect(UNTRANSLATED_SPEECH_MESSAGE).toBe(
      'This speech was delivered in Hindi. No English text is available.'
    )
    expect(SUPPLEMENTARY_PREFIX).toBe('From supplementary exchange — ')
  })
})
