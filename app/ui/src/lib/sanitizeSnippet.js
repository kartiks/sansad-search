// Snippet sanitisation for result cards (F05).
//
// The Phase-3 backend is contracted to emit HTML-safe snippets whose only live
// markup is the <mark> highlight tag. This module does NOT trust that contract
// blindly: it independently guarantees the card's own safety so that any HTML
// reaching a card renders as literal text and can never execute (F05 edge case:
// "HTML in snippet rendered as plain text; script tags do not execute").
//
// Strategy: escape every angle bracket and ampersand, then re-enable ONLY the
// <mark>/</mark> highlight tags. The result is safe to pass to
// dangerouslySetInnerHTML — <script>, <img onerror=…>, <b>, etc. all survive as
// inert literal text, while query-term highlighting still renders.

export function sanitizeSnippet(raw) {
  if (raw == null) return ''
  const escaped = String(raw)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // Re-enable only the highlight tag the backend is permitted to emit.
  return escaped
    .replace(/&lt;mark&gt;/g, '<mark>')
    .replace(/&lt;\/mark&gt;/g, '</mark>')
}
