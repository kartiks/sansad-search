import { describe, it, expect } from 'vitest'
import { safeHttpUrl } from '../lib/safeUrl.js'

describe('safeHttpUrl', () => {
  it('allows http and https URLs unchanged', () => {
    expect(safeHttpUrl('https://eparlib.sansad.in/handle/123')).toBe(
      'https://eparlib.sansad.in/handle/123'
    )
    expect(safeHttpUrl('http://example.org')).toBe('http://example.org')
  })

  it('rejects other schemes', () => {
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull()
    expect(safeHttpUrl(' JavaScript:alert(1)')).toBeNull()
    expect(safeHttpUrl('data:text/html,<script>alert(1)</script>')).toBeNull()
    expect(safeHttpUrl('vbscript:x')).toBeNull()
  })

  it('rejects relative URLs, empty values and non-strings', () => {
    expect(safeHttpUrl('/record/1')).toBeNull()
    expect(safeHttpUrl('')).toBeNull()
    expect(safeHttpUrl(null)).toBeNull()
    expect(safeHttpUrl(42)).toBeNull()
  })
})
