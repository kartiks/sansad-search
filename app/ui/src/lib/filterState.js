import { ALL_SOURCES, ALL_PROCEEDING_TYPES } from './constants.js'

export function defaultFilterState() {
  return {
    sources: [...ALL_SOURCES],
    proceeding_types: [...ALL_PROCEEDING_TYPES],
    date_from: null,
    date_to: null,
    speaker: null,
    session: null,
    subject: null,
  }
}

export function isDefaultFilterState(state) {
  if (!state) return true
  const def = defaultFilterState()
  return (
    sameArray(state.sources, def.sources) &&
    sameArray(state.proceeding_types, def.proceeding_types) &&
    !state.date_from &&
    !state.date_to &&
    !state.speaker &&
    !state.session &&
    !state.subject
  )
}

function sameArray(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false
  if (a.length !== b.length) return false
  const sa = [...a].sort()
  const sb = [...b].sort()
  return sa.every((v, i) => v === sb[i])
}

export function validateFilterState(state) {
  const errors = {}
  if (!state) return errors

  if (Array.isArray(state.sources) && state.sources.length === 0) {
    errors.sources = 'Select at least one source'
  }
  if (
    Array.isArray(state.proceeding_types) &&
    state.proceeding_types.length === 0
  ) {
    errors.proceeding_types = 'Select at least one proceeding type'
  }
  if (
    state.date_from &&
    state.date_to &&
    String(state.date_from) > String(state.date_to)
  ) {
    errors.date_range = 'From date must be before To date'
  }
  return errors
}

export function isFilterStateValid(state) {
  return Object.keys(validateFilterState(state)).length === 0
}

export function toApiFilters(state) {
  if (!state || isDefaultFilterState(state)) return null

  const out = {}
  if (
    Array.isArray(state.sources) &&
    !sameArray(state.sources, ALL_SOURCES)
  ) {
    out.sources = [...state.sources]
  }
  if (
    Array.isArray(state.proceeding_types) &&
    !sameArray(state.proceeding_types, ALL_PROCEEDING_TYPES)
  ) {
    out.proceeding_types = [...state.proceeding_types]
  }
  if (state.date_from) out.date_from = state.date_from
  if (state.date_to) out.date_to = state.date_to
  if (state.speaker && state.speaker.trim()) out.speaker = state.speaker.trim()
  if (state.session && state.session.trim()) out.session = state.session.trim()
  if (state.subject && state.subject.trim()) out.subject = state.subject.trim()
  return Object.keys(out).length === 0 ? null : out
}
