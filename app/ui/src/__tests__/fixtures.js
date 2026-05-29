export function makeSpeechResult(overrides = {}) {
  return {
    id: 'speech-1',
    record_type: 'speech',
    source: 'LS',
    proceeding_type: 'debate',
    proceeding_type_label: 'Debate',
    date: '2023-03-15',
    date_display: '15 March 2023',
    session_name: 'Budget Session 2023',
    subject: 'General Discussion on the Union Budget',
    snippet: 'The Finance Minister stated that <mark>PM</mark> infrastructure programmes will continue.',
    snippet_from_supplementary: false,
    is_translated: false,
    source_url: 'https://sansad.in/example',
    speaker_name: 'Jairam Ramesh',
    speaker_party: 'INC',
    speaker_constituency_or_state: 'Karnataka',
    speaker_name_unresolved: false,
    question_number: null,
    questioner_names: null,
    questioner_party: null,
    minister_name: null,
    ministry: null,
    ...overrides,
  }
}

export function makeQAResult(overrides = {}) {
  return {
    id: 'qa-1',
    record_type: 'qa',
    source: 'LS',
    proceeding_type: 'starred_question',
    proceeding_type_label: 'Starred Question',
    date: '2023-08-04',
    date_display: '4 August 2023',
    session_name: 'Monsoon Session 2023',
    subject: 'Implementation of National Health Mission',
    snippet: 'The Minister informed the House that <mark>NHM</mark> coverage has expanded.',
    snippet_from_supplementary: false,
    is_translated: false,
    source_url: 'https://sansad.in/qa-example',
    speaker_name: null,
    speaker_party: null,
    speaker_constituency_or_state: null,
    speaker_name_unresolved: false,
    question_number: 42,
    questioner_names: ['Shri A. Kumar'],
    questioner_party: 'BJP',
    minister_name: 'Dr. Mansukh Mandaviya',
    ministry: 'Ministry of Health and Family Welfare',
    ...overrides,
  }
}

export function makeSearchResponse(overrides = {}) {
  return {
    total: 47,
    total_display: '47',
    page: 1,
    total_pages: 3,
    per_page: 20,
    expansion_notice: [],
    results: [makeSpeechResult()],
    ...overrides,
  }
}

export function makeStatusResponse(overrides = {}) {
  return {
    status: 'ok',
    total_records: 350000,
    sources: {
      ca: { count: 8200, date_from: '1946-12-09', date_to: '1950-11-26' },
      ls: { count: 198000, date_from: '2014-06-04', date_to: '2026-05-15' },
      rs: { count: 143800, date_from: '2014-06-11', date_to: '2026-04-20' },
    },
    last_updated: '2026-05-15T14:30:00Z',
    ...overrides,
  }
}
