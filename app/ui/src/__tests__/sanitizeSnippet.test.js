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

  // Backend-shaped input: app/api/services/search.py html.escape()s the text and
  // adds <mark>. Entities must render once, not as literal "&#x27;".
  it('does not double-escape entities the backend already escaped', () => {
    expect(sanitizeSnippet('Member&#x27;s <mark>vote</mark>')).toBe(
      "Member's <mark>vote</mark>"
    )
    expect(sanitizeSnippet('Tom &amp; Jerry &quot;quoted&quot;')).toBe(
      'Tom &amp; Jerry "quoted"'
    )
  })

  it('renders backend-escaped tags as inert text', () => {
    const out = sanitizeSnippet('&lt;script&gt;alert(1)&lt;/script&gt; <mark>x</mark>')
    expect(out).toBe('&lt;script&gt;alert(1)&lt;/script&gt; <mark>x</mark>')
  })

  it('does not turn an escaped &lt;mark&gt; in the text into a live tag', () => {
    expect(sanitizeSnippet('a &lt;mark&gt; b')).toBe('a &lt;mark&gt; b')
  })

  it('decodes in a single pass (&amp;lt; stays the text "&lt;")', () => {
    expect(sanitizeSnippet('5 &amp;lt; 6')).toBe('5 &amp;lt; 6')
  })

  it('leaves unknown or invalid entities as literal text', () => {
    expect(sanitizeSnippet('&bogus; &#0; &#xD800;')).toBe(
      '&amp;bogus; &amp;#0; &amp;#xD800;'
    )
  })

  it('renders the decoded text correctly in the DOM', () => {
    const el = document.createElement('div')
    el.innerHTML = sanitizeSnippet('Member&#x27;s <mark>vote</mark> &amp; <b>x</b>')
    expect(el.textContent).toBe("Member's vote & <b>x</b>")
    expect(el.querySelectorAll('mark')).toHaveLength(1)
    expect(el.querySelector('b')).toBeNull()
  })
})
