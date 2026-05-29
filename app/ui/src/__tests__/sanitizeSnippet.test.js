import { describe, it, expect } from 'vitest'
import { sanitizeSnippet } from '../lib/sanitizeSnippet.js'

describe('sanitizeSnippet', () => {
  it('returns empty string for null/undefined', () => {
    expect(sanitizeSnippet(null)).toBe('')
    expect(sanitizeSnippet(undefined)).toBe('')
  })

  it('preserves <mark> highlight tags as live markup', () => {
    expect(sanitizeSnippet('The <mark>PM</mark> spoke.')).toBe(
      'The <mark>PM</mark> spoke.'
    )
  })

  it('escapes a raw <script> tag so it cannot execute', () => {
    const out = sanitizeSnippet('<script>alert(1)</script> hi')
    expect(out).not.toContain('<script>')
    expect(out).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
  })

  it('escapes raw formatting tags (no live <b>/<img>)', () => {
    expect(sanitizeSnippet('<b>x</b>')).toBe('&lt;b&gt;x&lt;/b&gt;')
    const img = sanitizeSnippet('<img src=x onerror=alert(1)>')
    expect(img).not.toContain('<img')
    expect(img).toContain('&lt;img src=x onerror=alert(1)&gt;')
  })

  it('escapes ampersands (prevents entity injection)', () => {
    expect(sanitizeSnippet('Tom & Jerry')).toBe('Tom &amp; Jerry')
  })

  it('keeps mark highlights while escaping surrounding hostile HTML', () => {
    const out = sanitizeSnippet('<script>x</script> <mark>term</mark> <b>y</b>')
    expect(out).toBe('&lt;script&gt;x&lt;/script&gt; <mark>term</mark> &lt;b&gt;y&lt;/b&gt;')
  })
})
