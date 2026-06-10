export const SOURCE_LABELS = {
  CA: 'Constituent Assembly',
  LS: 'Lok Sabha',
  RS: 'Rajya Sabha',
}

export const PROCEEDING_TYPE_LABELS = {
  debate: 'Debate',
  starred_question: 'Starred Question',
  unstarred_question: 'Unstarred Question',
  zero_hour: 'Zero Hour',
  short_notice_question: 'Short Notice Question',
  calling_attention: 'Calling Attention',
  short_duration_discussion: 'Short Duration Discussion',
  adjournment_motion: 'Adjournment Motion',
  private_member_bill: 'Private Member Bill',
}

export const ALL_SOURCES = ['CA', 'LS', 'RS']

export const ALL_PROCEEDING_TYPES = [
  'debate',
  'starred_question',
  'unstarred_question',
  'zero_hour',
  'short_notice_question',
  'calling_attention',
  'short_duration_discussion',
  'adjournment_motion',
  'private_member_bill',
]

export const SORT_OPTIONS = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'reverse_chronological', label: 'Newest first' },
  { value: 'chronological', label: 'Oldest first' },
]

export const SORT_LABELS = {
  relevance: 'Relevance',
  reverse_chronological: 'Newest first',
  chronological: 'Oldest first',
}

export const STATUS_ENDPOINT = '/api/status'

export const PER_PAGE = 20

export const MIN_QUERY_CHARS = 2

export const MAX_QUERY_LEN = 500

export const SEARCH_PLACEHOLDER =
  'Search parliamentary debates, questions, and speeches…'

export const TAGLINE =
  'Search the complete record of Indian parliamentary debates.'

export const VALIDATION_SHORT = 'Enter at least 2 characters to search.'

export const ERROR_STATE_TITLE = 'Search is temporarily unavailable.'

export const ERROR_STATE_BODY = 'Please try again.'

export const NO_RESULTS_BODY =
  'Try adjusting your search terms or removing filters.'

export const UNTRANSLATED_SPEECH_MESSAGE =
  'This speech was delivered in Hindi. No English text is available.'

export const SUPPLEMENTARY_PREFIX = 'From supplementary exchange — '

export function getProceedingTypeLabel(value) {
  if (value == null) return ''
  return PROCEEDING_TYPE_LABELS[value] || value
}

export function getSourceLabel(value) {
  if (value == null) return ''
  return SOURCE_LABELS[value] || value
}

// Body color palette (CA ochre, LS green, RS crimson)
export const BODY_COLORS = {
  CA: '#8B6914',
  LS: '#1E6B35',
  RS: '#9B1D20',
}

export const BODY_BADGE_STYLES = {
  CA: { background: '#F9F3E3', color: '#8B6914' },
  LS: { background: '#EAF4EE', color: '#1E6B35' },
  RS: { background: '#F9ECEC', color: '#9B1D20' },
}

// Canonical text strings
export const NO_ENGLISH_TEXT_RECORD =
  'This record was delivered in Hindi. No English text is available.'
export const RECORD_NOT_FOUND = 'Record not found'
export const RECORD_NOT_FOUND_DETAIL =
  "The record you're looking for does not exist or has been removed."
export const BACK_TO_RESULTS = '← Back to results'
export const BACK_TO_SEARCH = '← Search'
export const LOAD_PREVIOUS = '↑ Load 5 previous'
export const LOAD_NEXT = '↓ Load 5 next'
export const ADJACENT_ERROR = 'Could not load records. Try again.'
export const RAW_DOC_NOT_AVAILABLE = 'Raw document not available'
export const DEBUG_BADGE_LABEL = 'Debug'
