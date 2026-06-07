import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import RecordDetail from '../pages/RecordDetail.jsx'
import { makeRecordDetail, makeAdjacentRecord } from './fixtures.js'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

// ── Render helper ─────────────────────────────────────────────────────────────

function renderDetail(id = 'speech-1', state = null, extraRoutes = null) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: `/record/${id}`, state }]}>
      <Routes>
        <Route path="/record/:id" element={<RecordDetail />} />
        <Route path="/" element={<div data-testid="home-page">Home</div>} />
        {extraRoutes}
      </Routes>
    </MemoryRouter>
  )
}

function LocationDisplay() {
  const { pathname } = useLocation()
  return <div data-testid="location-display">{pathname}</div>
}

function renderDetailWithNav(id = 'speech-1', state = null) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: `/record/${id}`, state }]}>
      <LocationDisplay />
      <Routes>
        <Route path="/record/:id" element={<RecordDetail />} />
        <Route path="/" element={<div data-testid="home-page">Home</div>} />
        <Route path="/results" element={<div data-testid="results-page">Results</div>} />
      </Routes>
    </MemoryRouter>
  )
}

function mockFetch(record) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => record,
  }))
}

function mockFetch404() {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status: 404,
    json: async () => ({ error: 'not_found', message: 'Record not found.' }),
  }))
}

function mockFetchError() {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: false,
    status: 500,
    json: async () => null,
  }))
}

// ── Loading state ─────────────────────────────────────────────────────────────

describe('RecordDetail — loading state', () => {
  it('shows loading indicator initially', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    renderDetail()
    expect(screen.getByTestId('record-loading')).toBeInTheDocument()
  })
})

// ── 404 state ─────────────────────────────────────────────────────────────────

describe('RecordDetail — 404 state', () => {
  it('renders "Record not found." when 404', async () => {
    mockFetch404()
    renderDetail('nonexistent-id')
    await waitFor(() => expect(screen.getByTestId('record-not-found')).toBeInTheDocument())
    expect(screen.getByText('Record not found.')).toBeInTheDocument()
  })

  it('does not render a blank page or the detail component on 404', async () => {
    mockFetch404()
    renderDetail('nonexistent-id')
    await waitFor(() => expect(screen.getByTestId('record-not-found')).toBeInTheDocument())
    expect(screen.queryByTestId('record-detail')).toBeNull()
  })
})

// ── Error state ───────────────────────────────────────────────────────────────

describe('RecordDetail — error state', () => {
  it('renders error state with Retry button on server error', async () => {
    mockFetchError()
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-error')).toBeInTheDocument())
    expect(screen.getByTestId('retry-button')).toBeInTheDocument()
  })
})

// ── Successful render ─────────────────────────────────────────────────────────

describe('RecordDetail — successful render', () => {
  it('renders record detail after load', async () => {
    mockFetch(makeRecordDetail())
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
  })

  it('renders full_text_en as paragraphs', async () => {
    const record = makeRecordDetail({
      full_text_en: 'First paragraph.\n\nSecond paragraph.',
    })
    mockFetch(record)
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByText('First paragraph.')).toBeInTheDocument()
    expect(screen.getByText('Second paragraph.')).toBeInTheDocument()
  })

  it('renders null full_text_en message in text area', async () => {
    mockFetch(makeRecordDetail({ full_text_en: null }))
    renderDetail()
    await waitFor(() =>
      expect(screen.getByTestId('null-full-text-message')).toBeInTheDocument()
    )
    expect(screen.getByTestId('null-full-text-message').textContent).toBe(
      'This record was delivered in Hindi. No English text is available.'
    )
  })

  it('still renders all non-null metadata when full_text_en is null', async () => {
    mockFetch(makeRecordDetail({ full_text_en: null }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-source')).toBeInTheDocument()
    expect(screen.getByTestId('field-date')).toBeInTheDocument()
    expect(screen.getByTestId('null-full-text-message')).toBeInTheDocument()
  })
})

// ── Metadata fields ───────────────────────────────────────────────────────────

describe('RecordDetail — metadata fields', () => {
  it('shows date in DD Month YYYY format', async () => {
    mockFetch(makeRecordDetail())
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-date')).toHaveTextContent('15 March 2023')
  })

  it('shows time_of_day when not null', async () => {
    mockFetch(makeRecordDetail({ time_of_day: '14:35' }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-time-of-day')).toHaveTextContent('14:35')
  })

  it('omits time_of_day field when null', async () => {
    mockFetch(makeRecordDetail({ time_of_day: null }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.queryByTestId('field-time-of-day')).toBeNull()
  })

  it('shows lang_original always (en → "English")', async () => {
    mockFetch(makeRecordDetail({ lang_original: 'en' }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-lang-original')).toHaveTextContent('English')
  })

  it('shows lang_original hi → "Hindi"', async () => {
    mockFetch(makeRecordDetail({ lang_original: 'hi' }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-lang-original')).toHaveTextContent('Hindi')
  })

  it('shows lang_original mixed → "Bilingual"', async () => {
    mockFetch(makeRecordDetail({ lang_original: 'mixed' }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-lang-original')).toHaveTextContent('Bilingual')
  })

  it('shows page_reference as exactly "PDF page N" with no additional text', async () => {
    mockFetch(makeRecordDetail({ page_reference: 42 }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-page-reference').textContent).toBe('PDF page 42')
  })

  it('omits page_reference field when null — no "PDF page null" rendered', async () => {
    mockFetch(makeRecordDetail({ page_reference: null }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.queryByTestId('field-page-reference')).toBeNull()
    expect(screen.queryByText(/PDF page/)).toBeNull()
  })

  it('shows word_count as "N words"', async () => {
    mockFetch(makeRecordDetail({ word_count: 1820 }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-word-count')).toHaveTextContent('1820 words')
  })

  it('omits word_count when null', async () => {
    mockFetch(makeRecordDetail({ word_count: null }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.queryByTestId('field-word-count')).toBeNull()
  })

  it('shows source_url as View source link', async () => {
    mockFetch(makeRecordDetail({ source_url: 'https://example.com/record' }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    const link = screen.getByText('View source ↗')
    expect(link).toHaveAttribute('href', 'https://example.com/record')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('omits source_url link when null', async () => {
    mockFetch(makeRecordDetail({ source_url: null }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.queryByText('View source ↗')).toBeNull()
  })

  it('shows speaker name without unresolved badge when speaker_name_unresolved=true', async () => {
    mockFetch(makeRecordDetail({ speaker_name: 'Unknown Name', speaker_name_unresolved: true }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-speaker-name')).toHaveTextContent('Unknown Name')
    expect(screen.queryByTestId('name-unresolved')).toBeNull()
  })

  it('does not show unresolved note when speaker_name_unresolved=false', async () => {
    mockFetch(makeRecordDetail({ speaker_name_unresolved: false }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.queryByTestId('name-unresolved')).toBeNull()
  })
})

// ── Position indicator ────────────────────────────────────────────────────────

describe('RecordDetail — position indicator', () => {
  it('shows [N] of [M] where M is sitting_total', async () => {
    mockFetch(makeRecordDetail({ sequence_within_sitting: 7, sitting_total: 20 }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('position-indicator')).toHaveTextContent('7 of 20')
  })
})

// ── Lok Sabha term display ────────────────────────────────────────────────────

describe('RecordDetail — Lok Sabha term display', () => {
  it('renders "17th Lok Sabha" for an LS record with lok_sabha_number 17', async () => {
    mockFetch(makeRecordDetail({ source: 'LS', lok_sabha_number: 17 }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('field-lok-sabha-number')).toHaveTextContent('17th Lok Sabha')
  })

  it('renders correct ordinal suffixes (21st, 22nd, 23rd)', async () => {
    for (const [n, expected] of [[21, '21st Lok Sabha'], [22, '22nd Lok Sabha'], [23, '23rd Lok Sabha']]) {
      mockFetch(makeRecordDetail({ source: 'LS', lok_sabha_number: n }))
      const { unmount } = renderDetail()
      await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
      expect(screen.getByTestId('field-lok-sabha-number')).toHaveTextContent(expected)
      unmount()
    }
  })

  it('RS record renders no "Lok Sabha" text and no lok_sabha field', async () => {
    mockFetch(makeRecordDetail({ source: 'RS', lok_sabha_number: null, speaker_constituency_or_state: 'Maharashtra' }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.queryByTestId('field-lok-sabha-number')).toBeNull()
    expect(screen.queryByText(/Lok Sabha/)).toBeNull()
  })

  it('omits the field when an LS record has null lok_sabha_number', async () => {
    mockFetch(makeRecordDetail({ source: 'LS', lok_sabha_number: null }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.queryByTestId('field-lok-sabha-number')).toBeNull()
  })
})

// ── Adjacent load controls — initial state ────────────────────────────────────

describe('RecordDetail — adjacent load controls', () => {
  it('renders Load 5 previous / Load 5 next controls', async () => {
    mockFetch(makeRecordDetail({ has_prev: true, has_next: true }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('load-prev-button')).toHaveTextContent('Load 5 previous')
    expect(screen.getByTestId('load-next-button')).toHaveTextContent('Load 5 next')
  })

  it('Load 5 previous enabled when has_prev true', async () => {
    mockFetch(makeRecordDetail({ has_prev: true }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('load-prev-button')).not.toBeDisabled()
  })

  it('Load 5 previous disabled and IN the DOM when has_prev false (lower boundary)', async () => {
    mockFetch(makeRecordDetail({ sequence_within_sitting: 1, has_prev: false, has_next: true }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    const btn = screen.getByTestId('load-prev-button')
    expect(btn).toBeInTheDocument()
    expect(btn).toBeDisabled()
  })

  it('Load 5 next disabled and IN the DOM when has_next false (upper boundary)', async () => {
    mockFetch(makeRecordDetail({ has_prev: true, has_next: false }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    const btn = screen.getByTestId('load-next-button')
    expect(btn).toBeInTheDocument()
    expect(btn).toBeDisabled()
  })

  it('both controls disabled for single-record sitting', async () => {
    mockFetch(makeRecordDetail({ sequence_within_sitting: 1, sitting_total: 1, has_prev: false, has_next: false }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('load-prev-button')).toBeDisabled()
    expect(screen.getByTestId('load-next-button')).toBeDisabled()
  })

  it('disabled control is not hidden (no display:none)', async () => {
    mockFetch(makeRecordDetail({ has_prev: false, has_next: true }))
    renderDetail()
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('load-prev-button').style.display).not.toBe('none')
  })
})

// ── Back navigation ───────────────────────────────────────────────────────────

describe('RecordDetail — back navigation', () => {
  it('shows "Back to results" button when state.from=search', async () => {
    mockFetch(makeRecordDetail())
    renderDetail('speech-1', { from: 'search' })
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('back-to-results')).toBeInTheDocument()
    expect(screen.queryByTestId('back-to-search')).toBeNull()
  })

  it('shows "← Search" link when no referrer state (direct URL access)', async () => {
    mockFetch(makeRecordDetail())
    renderDetail('speech-1', null)
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('back-to-search')).toBeInTheDocument()
    expect(screen.queryByTestId('back-to-results')).toBeNull()
  })

  it('Search link on direct access points to homepage /', async () => {
    mockFetch(makeRecordDetail())
    renderDetail('speech-1', null)
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())
    expect(screen.getByTestId('back-to-search')).toHaveAttribute('href', '/')
  })

  it('clicking "Back to results" navigates to resultsPath, not just one step back', async () => {
    mockFetch(makeRecordDetail())
    renderDetailWithNav('speech-1', { from: 'search', resultsPath: '/results?q=water' })
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('back-to-results'))

    await waitFor(() =>
      expect(screen.getByTestId('location-display')).toHaveTextContent('/results')
    )
    expect(screen.getByTestId('results-page')).toBeInTheDocument()
  })

  it('falling back to "/" when resultsPath is absent', async () => {
    mockFetch(makeRecordDetail())
    renderDetailWithNav('speech-1', { from: 'search' })
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('back-to-results'))

    await waitFor(() =>
      expect(screen.getByTestId('location-display')).toHaveTextContent('/')
    )
    expect(screen.getByTestId('home-page')).toBeInTheDocument()
  })
})

// ── Inline adjacent loading behavior ──────────────────────────────────────────

// Dispatches the record fetch and the /adjacent fetch by URL. `adjacentQueue`
// is an array of responses returned in order for successive /adjacent calls.
function mockRecordAndAdjacent(record, adjacentQueue) {
  let idx = 0
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/adjacent')) {
      const resp = adjacentQueue[Math.min(idx, adjacentQueue.length - 1)]
      idx += 1
      return Promise.resolve({ ok: true, status: 200, json: async () => resp })
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => record })
  }))
}

describe('RecordDetail — inline adjacent loading', () => {
  it('clicking Load 5 next appends records without page navigation', async () => {
    mockRecordAndAdjacent(
      makeRecordDetail({ id: 'speech-1', sequence_within_sitting: 7, has_next: true }),
      [{
        direction: 'next',
        records: [
          makeAdjacentRecord({ id: 'next-a', sequence_within_sitting: 8, subject: 'Next subject A' }),
        ],
        has_more: false,
      }]
    )
    renderDetailWithNav('speech-1')
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('load-next-button'))

    await waitFor(() =>
      expect(screen.getByTestId('adjacent-record-next-a')).toBeInTheDocument()
    )
    // URL did not change.
    expect(screen.getByTestId('location-display')).toHaveTextContent('/record/speech-1')
  })

  it('clicking Load 5 previous prepends records; focal stays in the DOM', async () => {
    mockRecordAndAdjacent(
      makeRecordDetail({ id: 'speech-1', sequence_within_sitting: 10, has_prev: true }),
      [{
        direction: 'prev',
        records: [
          makeAdjacentRecord({ id: 'prev-a', sequence_within_sitting: 9, subject: 'Prev subject A' }),
        ],
        has_more: false,
      }]
    )
    renderDetailWithNav('speech-1')
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('load-prev-button'))

    await waitFor(() =>
      expect(screen.getByTestId('adjacent-record-prev-a')).toBeInTheDocument()
    )
    // Focal record still present.
    expect(screen.getByTestId('record-detail')).toBeInTheDocument()
    expect(screen.getByTestId('location-display')).toHaveTextContent('/record/speech-1')
  })

  it('control stays enabled when has_more true, disables when next batch has_more false', async () => {
    mockRecordAndAdjacent(
      makeRecordDetail({ id: 'speech-1', sequence_within_sitting: 7, has_next: true }),
      [
        {
          direction: 'next',
          records: [makeAdjacentRecord({ id: 'n8', sequence_within_sitting: 8 })],
          has_more: true,
        },
        {
          direction: 'next',
          records: [makeAdjacentRecord({ id: 'n9', sequence_within_sitting: 9 })],
          has_more: false,
        },
      ]
    )
    renderDetailWithNav('speech-1')
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('load-next-button'))
    await waitFor(() => expect(screen.getByTestId('adjacent-record-n8')).toBeInTheDocument())
    expect(screen.getByTestId('load-next-button')).not.toBeDisabled()

    fireEvent.click(screen.getByTestId('load-next-button'))
    await waitFor(() => expect(screen.getByTestId('adjacent-record-n9')).toBeInTheDocument())
    expect(screen.getByTestId('load-next-button')).toBeDisabled()
  })

  it('clicking a disabled control loads nothing and does not navigate', async () => {
    mockRecordAndAdjacent(
      makeRecordDetail({ id: 'speech-1', sequence_within_sitting: 1, has_prev: false, has_next: true }),
      [{ direction: 'prev', records: [], has_more: false }]
    )
    renderDetailWithNav('speech-1')
    await waitFor(() => expect(screen.getByTestId('record-detail')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('load-prev-button'))

    expect(screen.queryByTestId('adjacent-prev-records')).toBeNull()
    expect(screen.getByTestId('location-display')).toHaveTextContent('/record/speech-1')
  })
})
