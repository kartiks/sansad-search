// Snippet sanitisation for result cards (F05).
//
// The backend HTML-escapes snippet text and wraps query terms in <mark>
// (app/api/services/search.py, _build_snippet). So a snippet arrives as e.g.
// `Member&#x27;s <mark>vote</mark>`.
//
// This module does NOT trust that contract blindly: any HTML reaching a card
// must render as literal text and never execute (F05 edge case: "HTML in
// snippet rendered as plain text; script tags do not execute").
//
// Strategy: split the snippet on the <mark>/</mark> tags. Each text segment is
// decoded to plain text (so backend entities like &#x27; are not escaped a
// second time) and then escaped exactly once. Only the <mark> tags stay live,
// so the result is safe for dangerouslySetInnerHTML.

const MARK_TAG = /(<\/?mark>)/i

const NAMED_ENTITIES = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
}

function decodeEntities(text) {
  // Single pass, so `&amp;lt;` decodes to the text `&lt;`, not to `<`.
  return text.replace(/&(#\d+|#x[0-9a-f]+|[a-z]+);/gi, (match, body) => {
    if (body[0] === '#') {
      const code =
        body[1] === 'x' || body[1] === 'X'
          ? parseInt(body.slice(2), 16)
          : parseInt(body.slice(1), 10)
      if (!Number.isFinite(code) || code < 1 || code > 0x10ffff) return match
      if (code >= 0xd800 && code <= 0xdfff) return match
      return String.fromCodePoint(code)
    }
    const named = NAMED_ENTITIES[body.toLowerCase()]
    return named === undefined ? match : named
  })
}

function escapeText(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function sanitizeSnippet(raw) {
  if (raw == null) return ''
  return String(raw)
    .split(MARK_TAG)
    .map((part) => {
      if (/^<mark>$/i.test(part)) return '<mark>'
      if (/^<\/mark>$/i.test(part)) return '</mark>'
      return escapeText(decodeEntities(part))
    })
    .join('')
}
