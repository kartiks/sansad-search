// Filter state <-> URL query params, so a results URL is shareable and the
// browser's Back button undoes a filter change.
//
// Only non-default filters are written:
//   source=LS,RS  type=debate,zero_hour  from=2020-01-01  to=2024-12-31
//   speaker=…     session=…              subject=…

import { compactFilters, sanitizeStoredFilters } from './filterState.js'

const LIST_PARAMS = { sources: 'source', proceeding_types: 'type' }
const TEXT_PARAMS = {
  date_from: 'from',
  date_to: 'to',
  speaker: 'speaker',
  session: 'session',
  subject: 'subject',
}

export const FILTER_PARAM_NAMES = [
  ...Object.values(LIST_PARAMS),
  ...Object.values(TEXT_PARAMS),
]

function splitList(value) {
  return value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean)
}

export function filtersFromSearchParams(params) {
  const stored = {}
  for (const [key, name] of Object.entries(LIST_PARAMS)) {
    const value = params.get(name)
    if (value) stored[key] = splitList(value)
  }
  for (const [key, name] of Object.entries(TEXT_PARAMS)) {
    const value = params.get(name)
    if (value) stored[key] = value
  }
  return sanitizeStoredFilters(stored)
}

// Writes the filters into `params` (a URLSearchParams), replacing any filter
// params already there. Returns the same object.
export function setFilterSearchParams(params, filters) {
  FILTER_PARAM_NAMES.forEach((name) => params.delete(name))
  const compact = compactFilters(filters)
  for (const [key, name] of Object.entries(LIST_PARAMS)) {
    if (compact[key]) params.set(name, compact[key].join(','))
  }
  for (const [key, name] of Object.entries(TEXT_PARAMS)) {
    if (compact[key]) params.set(name, compact[key])
  }
  return params
}

// URL for a results page. Sort is omitted when it is the default.
export function buildSearchUrl({ query, filters, sort, page = 1 }) {
  const params = new URLSearchParams()
  params.set('q', query)
  params.set('page', String(page))
  if (sort && sort !== 'relevance') params.set('sort', sort)
  setFilterSearchParams(params, filters)
  return `/search?${params.toString()}`
}
