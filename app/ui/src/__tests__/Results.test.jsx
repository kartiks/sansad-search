import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('../lib/cookie.js', () => ({
  areCookiesEnabled: vi.fn().mockReturnValue(true),
  readCookie: vi.fn().mockReturnValue(null),
  writeCookie: vi.fn(),
  deleteCookie: vi.fn(),
  trimRecentToFit: vi.fn((entries) => entries),
  RECENT_COOKIE: 'ss_recent',
  SAVED_COOKIE: 'ss_saved',
  MAX_COMBINED_BYTES: 4096,
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

import Results from '../pages/Results.jsx'
import {
  makeSearchResponse,
  makeSpeechResult,
  makeQAResult,
} from './fixtures.js'
import * as cookieModule from '../lib/cookie.js'
import { ALL_PROCEEDING_TYPES } from '../lib/constants.js'

function LocationCapture() {
  const loc = useLocation()
  return <div data-testid="loc">{loc.pathname + loc.search}</div>
}

function renderResults(initial = '/search?q=rights&page=1') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/search" element={<Results />} />
        <Route
          path="/"
          element={<div data-testid="home-page">home</div>}
        />
      </Routes>
      <LocationCapture />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  global.fetch = vi.fn()
  cookieModule.areCookiesEnabled.mockReturnValue(true)
  cookieModule.readCookie.mockReturnValue(null)
  cookieModule.trimRecentToFit.mockImplementation((entries) => entries)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Results — loading and rendering', () => {
  it('shows 5 skeleton cards while loading', async () => {
    global.fetch.mockImplementation(() => new Promise(() => {}))
    renderResults()
    const skeletons = await screen.findAllByTestId('skeleton-card')
    expect(skeletons).toHaveLength(5)
  })

  it('renders result cards after fetch resolves', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 47,
          total_display: '47',
          total_pages: 3,
          results: [makeSpeechResult({ id: 'a' })],
        }),
    })
    renderResults()
    await screen.findByTestId('results-list')
    expect(screen.getByTestId('speech-card')).toBeInTheDocument()
  })

  it('renders the result count', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 47,
          total_display: '47',
          total_pages: 3,
          results: [makeSpeechResult({ id: 'a' })],
        }),
    })
    renderResults('/search?q=fundamental+rights&page=1')
    const count = await screen.findByTestId('result-count')
    expect(count.textContent).toContain('47 results')
    expect(count.textContent).toContain('fundamental rights')
  })

  it('renders "10,000+ results" when total_display reports 10,000+', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 25000,
          total_display: '10,000+',
          total_pages: 500,
          results: [makeSpeechResult()],
        }),
    })
    renderResults()
    await waitFor(() => {
      expect(screen.getByTestId('result-count').textContent).toContain('10,000+ results')
    })
  })

  it('shows "0 results" + empty state when no records match', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 0,
          total_display: '0',
          total_pages: 1,
          results: [],
        }),
    })
    renderResults('/search?q=zzzz123abc&page=1')
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByTestId('result-count').textContent).toContain('0 results')
  })
})

describe('Results — error and retry', () => {
  it('shows error state with Retry button on API failure', async () => {
    global.fetch.mockRejectedValue(new TypeError('Failed to fetch'))
    renderResults()
    expect(await screen.findByTestId('error-state')).toBeInTheDocument()
    expect(screen.getByTestId('retry-button')).toBeInTheDocument()
  })

  it('Retry re-issues the fetch', async () => {
    global.fetch
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () =>
          makeSearchResponse({
            total: 1,
            total_display: '1',
            total_pages: 1,
            results: [makeSpeechResult()],
          }),
      })
    renderResults()
    await screen.findByTestId('error-state')
    fireEvent.click(screen.getByTestId('retry-button'))
    expect(await screen.findByTestId('results-list')).toBeInTheDocument()
  })
})

describe('Results — expansion notice', () => {
  it('renders "Also searching for:" when expansion present', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          expansion_notice: ['Prime Minister', 'Chief Minister'],
        }),
    })
    renderResults()
    await waitFor(() => {
      expect(screen.getByTestId('expansion-notice').textContent).toContain(
        'Also searching for: Prime Minister, Chief Minister'
      )
    })
  })

  it('omits the expansion notice when none returned', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse({ expansion_notice: [] }),
    })
    renderResults()
    await screen.findByTestId('results-list')
    expect(screen.queryByTestId('expansion-notice')).toBeNull()
  })
})

describe('Results — sort dropdown (F06)', () => {
  it('defaults to Relevance for new search from URL with no sort param', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 1,
          total_display: '1',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=rights&page=1')
    const dropdown = await screen.findByTestId('sort-dropdown')
    expect(dropdown).toHaveValue('relevance')
  })

  it('changing sort updates URL and re-fetches', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 1,
          total_display: '1',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=rights&page=1')
    const dropdown = await screen.findByTestId('sort-dropdown')
    fireEvent.change(dropdown, { target: { value: 'chronological' } })
    await waitFor(() => {
      expect(screen.getByTestId('loc').textContent).toContain('sort=chronological')
    })
    // The second fetch carries the new sort
    const calls = global.fetch.mock.calls
    const lastBody = JSON.parse(calls[calls.length - 1][1].body)
    expect(lastBody.sort).toBe('chronological')
  })

  it('persists sort across query refinements', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 1,
          total_display: '1',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=rights&page=1&sort=chronological')

    await screen.findByTestId('sort-dropdown')
    expect(screen.getByTestId('sort-dropdown')).toHaveValue('chronological')

    const input = screen.getByTestId('results-search-input')
    fireEvent.change(input, { target: { value: 'amendment' } })
    fireEvent.click(screen.getByTestId('results-search-submit'))

    await waitFor(() => {
      const loc = screen.getByTestId('loc').textContent
      expect(loc).toContain('q=amendment')
      expect(loc).toContain('sort=chronological')
    })
  })

  it('result count display does NOT change when sort changes', async () => {
    let callCount = 0
    global.fetch.mockImplementation(() => {
      callCount += 1
      return Promise.resolve({
        ok: true,
        json: async () =>
          makeSearchResponse({
            total: 47,
            total_display: '47',
            total_pages: 3,
            results: [makeSpeechResult({ id: `r-${callCount}` })],
          }),
      })
    })
    renderResults('/search?q=rights&page=1')
    await waitFor(() => {
      expect(screen.getByTestId('result-count').textContent).toContain('47')
    })

    fireEvent.change(screen.getByTestId('sort-dropdown'), {
      target: { value: 'reverse_chronological' },
    })

    await waitFor(() => {
      expect(screen.getByTestId('result-count').textContent).toContain('47')
    })
  })

  it('Sort param "reverse_chronological" maps to Newest first', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 1,
          total_display: '1',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=rights&page=1&sort=reverse_chronological')
    const dropdown = await screen.findByTestId('sort-dropdown')
    expect(dropdown).toHaveValue('reverse_chronological')
  })
})

describe('Results — pagination (F05)', () => {
  it('renders pagination when total_pages > 1', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 47,
          total_display: '47',
          total_pages: 3,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=rights&page=1')
    await screen.findByLabelText('Pagination')
    expect(screen.getByLabelText('Next page')).toBeInTheDocument()
  })

  it('URL on page change includes &page=N', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 60,
          total_display: '60',
          total_pages: 3,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=rights&page=1')
    await screen.findByLabelText('Pagination')
    fireEvent.click(screen.getByText('3'))
    await waitFor(() => {
      expect(screen.getByTestId('loc').textContent).toContain('page=3')
    })
  })

  it('loading /search?q=X&page=3 directly loads page 3 of that query', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 100,
          total_display: '100',
          page: 3,
          total_pages: 5,
          results: [makeSpeechResult({ id: 'page3-1' })],
        }),
    })
    renderResults('/search?q=rights&page=3')
    await screen.findByTestId('results-list')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.page).toBe(3)
    expect(body.query).toBe('rights')
  })

  it('a URL with no page param defaults to page 1 of the query (POST body page === 1)', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 12,
          total_display: '12',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=rights')
    await screen.findByTestId('results-list')
    const body = JSON.parse(global.fetch.mock.calls[0][1].body)
    expect(body.page).toBe(1)
    expect(body.query).toBe('rights')
  })
})

describe('Results — search box pre-population (F02)', () => {
  it('pre-populates the persistent search box with the current URL query on load', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 1,
          total_display: '1',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=fundamental+rights&page=1')
    const input = await screen.findByTestId('results-search-input')
    expect(input).toHaveValue('fundamental rights')
  })
})

describe('Results — refinement (F02)', () => {
  it('refining the query keeps the user on /search', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 1,
          total_display: '1',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=rights&page=1')
    await screen.findByTestId('results-list')
    fireEvent.change(screen.getByTestId('results-search-input'), {
      target: { value: 'amendment' },
    })
    fireEvent.click(screen.getByTestId('results-search-submit'))
    await waitFor(() => {
      expect(screen.getByTestId('loc').textContent).toContain('q=amendment')
    })
  })

  it('shows inline validation if refinement query is < 2 chars', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 1,
          total_display: '1',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
    renderResults('/search?q=rights&page=1')
    await screen.findByTestId('results-list')
    fireEvent.change(screen.getByTestId('results-search-input'), {
      target: { value: ' a ' },
    })
    fireEvent.click(screen.getByTestId('results-search-submit'))
    expect(await screen.findByTestId('results-validation')).toBeInTheDocument()
  })
})

describe('Results — direct /search without query', () => {
  it('redirects to home', async () => {
    renderResults('/search')
    await screen.findByTestId('home-page')
  })
})

describe('Results — Q+A dispatch', () => {
  it('renders QACard for record_type=qa', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 1,
          total_display: '1',
          total_pages: 1,
          results: [makeQAResult()],
        }),
    })
    renderResults('/search?q=health&page=1')
    expect(await screen.findByTestId('qa-card')).toBeInTheDocument()
  })
})

describe('Results — index status footer', () => {
  it('renders an "Index status" link', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 1,
          total_display: '1',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
    renderResults()
    const link = await screen.findByTestId('index-status-link')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/index-status')
    expect(link).toHaveTextContent('Index status')
  })
})

describe('Results — filter chips and modal (F03 UI)', () => {
  beforeEach(() => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 10,
          total_display: '10',
          total_pages: 1,
          results: [makeSpeechResult()],
        }),
    })
  })

  it('filter chips row is not shown when no filters are active', async () => {
    renderResults()
    await screen.findByTestId('results-list')
    expect(screen.queryByTestId('filter-chips-row')).toBeNull()
  })

  it('Advanced Search link button is present in the header', async () => {
    renderResults()
    await screen.findByTestId('results-list')
    expect(screen.getByTestId('results-advanced-search-link')).toBeInTheDocument()
  })

  it('clicking Advanced Search opens the modal', async () => {
    renderResults()
    await screen.findByTestId('results-list')
    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    expect(await screen.findByTestId('advanced-search-modal')).toBeInTheDocument()
  })

  it('modal close button closes the modal', async () => {
    renderResults()
    await screen.findByTestId('results-list')
    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('advanced-search-modal')
    fireEvent.click(screen.getByTestId('modal-close'))
    await waitFor(() => {
      expect(screen.queryByTestId('advanced-search-modal')).toBeNull()
    })
  })

  it('applying a body filter via modal shows a filter chip', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })
    const chips = screen.getAllByTestId('filter-chip')
    expect(chips.length).toBeGreaterThan(0)
    const chipText = chips.map((c) => c.textContent).join(' ')
    expect(chipText).toContain('Lok Sabha')
  })

  it('applying filter includes it in the next API request body', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      const calls = global.fetch.mock.calls
      const lastBody = JSON.parse(calls[calls.length - 1][1].body)
      expect(lastBody.filters).toBeDefined()
      expect(lastBody.filters.sources).toEqual(expect.arrayContaining(['LS', 'RS']))
      expect(lastBody.filters.sources).not.toContain('CA')
    })
  })

  it('chip x removes the filter and re-fetches without it', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })

    const removeBtn = screen.getByTestId('filter-chip-remove')
    fireEvent.click(removeBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('filter-chips-row')).toBeNull()
    })

    const calls = global.fetch.mock.calls
    const lastBody = JSON.parse(calls[calls.length - 1][1].body)
    expect(lastBody.filters?.sources).toBeUndefined()
  })

  it('"Clear all" chips link resets all filters', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('filter-chips-clear-all'))

    await waitFor(() => {
      expect(screen.queryByTestId('filter-chips-row')).toBeNull()
    })
  })

  it('filter persists across query refinements (not reset on new query)', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })

    const input = screen.getByTestId('results-search-input')
    fireEvent.change(input, { target: { value: 'new query' } })
    fireEvent.click(screen.getByTestId('results-search-submit'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })

    await waitFor(() => {
      const calls = global.fetch.mock.calls
      const lastBody = JSON.parse(calls[calls.length - 1][1].body)
      expect(lastBody.filters?.sources).toEqual(['RS'])
    })
  })

  it('zero-selection validation: all bodies unchecked shows validation, no new search', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    const fetchCallsBefore = global.fetch.mock.calls.length

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    fireEvent.click(screen.getByTestId('source-chip-RS'))

    const applyBtn = screen.getByTestId('modal-apply')
    expect(applyBtn).toBeDisabled()
    fireEvent.click(applyBtn)

    expect(global.fetch.mock.calls.length).toBe(fetchCallsBefore)
    expect(screen.getByTestId('source-validation')).toBeInTheDocument()
  })

  it('date validation: From > To shows error, Apply disabled', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('date-from-input')
    fireEvent.change(screen.getByTestId('date-from-input'), {
      target: { value: '2022-06-01' },
    })
    fireEvent.change(screen.getByTestId('date-to-input'), {
      target: { value: '2021-01-01' },
    })
    expect(screen.getByTestId('date-validation')).toBeInTheDocument()
    expect(screen.getByTestId('modal-apply')).toBeDisabled()
  })

  it('speaker chip shows when speaker filter applied', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('speaker-input')
    fireEvent.change(screen.getByTestId('speaker-input'), {
      target: { value: 'Singh' },
    })
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      const chips = screen.getAllByTestId('filter-chip')
      const chipText = chips.map((c) => c.textContent).join(' ')
      expect(chipText).toContain('Speaker: Singh')
    })
  })

  it('session chip shows when session filter applied', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('session-input')
    fireEvent.change(screen.getByTestId('session-input'), {
      target: { value: 'Budget Session 2023' },
    })
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      const chips = screen.getAllByTestId('filter-chip')
      const chipText = chips.map((c) => c.textContent).join(' ')
      expect(chipText).toContain('Session: Budget Session 2023')
    })
  })

  it('subject chip shows when subject filter applied', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('subject-input')
    fireEvent.change(screen.getByTestId('subject-input'), {
      target: { value: 'Railways' },
    })
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      const chips = screen.getAllByTestId('filter-chip')
      const chipText = chips.map((c) => c.textContent).join(' ')
      expect(chipText).toContain('Subject: Railways')
    })
  })

  it('no-results state with active filters shows the clear-filters affordance', async () => {
    // Filtered query returns zero results: empty state must render together with
    // the chips row "Clear all" control (F03 "No results with active filters").
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeSearchResponse({
          total: 0,
          total_display: '0',
          total_pages: 1,
          results: [],
        }),
    })
    renderResults('/search?q=fundamental+rights&page=1')
    await screen.findByTestId('empty-state')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })
    // Both the empty state and the clear-filters control are present together.
    expect(screen.getByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByTestId('filter-chips-clear-all')).toBeInTheDocument()
  })

  it('modal pre-populates from active filter state when reopened', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')

    expect(screen.getByTestId('source-chip-CA')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('source-chip-LS')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('source-chip-RS')).toHaveAttribute('aria-pressed', 'true')
  })
})

describe('Results — F08 Search History wiring', () => {
  it('selecting a recent entry resets active filters and sort to defaults in the API call', async () => {
    // Pre-populate one recent entry so the dropdown shows a clickable item
    cookieModule.readCookie.mockImplementation((name) =>
      name === 'ss_recent'
        ? [{ query: 'water rights', timestamp: Date.now() }]
        : null
    )
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse({ results: [makeSpeechResult()] }),
    })
    // Render with a non-default filter (RS-only) and non-default sort active
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/search',
            search: '?q=rights&page=1&sort=reverse_chronological',
            state: {
              filters: {
                sources: ['RS'],
                proceeding_types: [...ALL_PROCEEDING_TYPES],
                date_from: null,
                date_to: null,
                speaker: null,
                session: null,
              },
            },
          },
        ]}
      >
        <Routes>
          <Route path="/search" element={<Results />} />
          <Route path="/" element={<div data-testid="home-page">home</div>} />
        </Routes>
        <LocationCapture />
      </MemoryRouter>
    )
    await screen.findByTestId('results-list')

    // Clear the input then focus it — triggers the recent-searches dropdown
    const input = screen.getByTestId('results-search-input')
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.focus(input)

    await screen.findByTestId('recent-searches-dropdown')
    // Click the recent entry — handleRecentSelect resets filters and sort
    fireEvent.click(screen.getByRole('button', { name: 'Search for water rights' }))

    await waitFor(() => {
      const calls = global.fetch.mock.calls
      const lastBody = JSON.parse(calls[calls.length - 1][1].body)
      // Default filter state → toApiFilters returns null → no filters key in body (Gap 1)
      expect(lastBody.filters).toBeUndefined()
      // No sort param in URL after re-run → defaults to 'relevance' (Gap 3)
      expect(lastBody.sort).toBe('relevance')
    })
  })

  it('running a saved entry restores stored filter state exactly and uses default sort', async () => {
    const savedFilters = {
      sources: ['RS'],
      proceeding_types: ['starred_question'],
      date_from: '2020-01-01',
      date_to: null,
      speaker: null,
      session: null,
    }
    cookieModule.readCookie.mockImplementation((name) =>
      name === 'ss_saved'
        ? [
            {
              id: 'saved-1',
              name: 'RS Starred 2020',
              query: 'health policy',
              filters: savedFilters,
              timestamp: Date.now(),
            },
          ]
        : null
    )
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse({ results: [makeSpeechResult()] }),
    })
    // Render at non-default sort so we can verify sort resets to relevance (Gap 3)
    renderResults('/search?q=rights&page=1&sort=reverse_chronological')
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-bookmark-btn'))
    await screen.findByTestId('saved-searches-panel')
    // Click the run button on the saved entry (Gap 2)
    fireEvent.click(screen.getByTestId('saved-search-run-btn'))

    await waitFor(() => {
      const calls = global.fetch.mock.calls
      const lastBody = JSON.parse(calls[calls.length - 1][1].body)
      // Exact stored filter values must be present in the request (Gap 2)
      expect(lastBody.filters).toBeDefined()
      expect(lastBody.filters.sources).toEqual(['RS'])
      expect(lastBody.filters.proceeding_types).toEqual(['starred_question'])
      expect(lastBody.filters.date_from).toBe('2020-01-01')
      // History re-run always uses default sort (Gap 3)
      expect(lastBody.sort).toBe('relevance')
    })
  })

  it('submitting a query from Results auto-records it to recent history', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse({ results: [makeSpeechResult()] }),
    })
    renderResults()
    await screen.findByTestId('results-list')

    const input = screen.getByTestId('results-search-input')
    fireEvent.change(input, { target: { value: 'parliamentary procedure' } })
    fireEvent.click(screen.getByTestId('results-search-submit'))

    // recordSearch is wired into onSubmit — writeCookie must be called for ss_recent (Gap 4)
    await waitFor(() => {
      expect(cookieModule.writeCookie).toHaveBeenCalledWith(
        'ss_recent',
        expect.arrayContaining([
          expect.objectContaining({ query: 'parliamentary procedure' }),
        ]),
        { expires: 30 }
      )
    })
  })

  it('save current search button captures the active query and filter state', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse({ results: [makeSpeechResult()] }),
    })
    renderResults('/search?q=fundamental+rights&page=1')
    await screen.findByTestId('results-list')

    // Apply a non-default filter via the modal (uncheck CA, leaving LS + RS)
    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    await screen.findByTestId('source-chip-CA')
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))
    await waitFor(() => {
      expect(screen.queryByTestId('advanced-search-modal')).toBeNull()
    })

    // Open saved panel and click "Save current search" (Gap 5)
    fireEvent.click(screen.getByTestId('results-bookmark-btn'))
    await screen.findByTestId('saved-searches-panel')
    fireEvent.click(screen.getByTestId('saved-search-save-btn'))

    await waitFor(() => {
      const savedCalls = cookieModule.writeCookie.mock.calls.filter(
        (c) => c[0] === 'ss_saved'
      )
      expect(savedCalls.length).toBeGreaterThan(0)
      const savedEntries = savedCalls[savedCalls.length - 1][1]
      expect(savedEntries).toHaveLength(1)
      // Must capture the current URL query
      expect(savedEntries[0].query).toBe('fundamental rights')
      // Must capture the active filter state (CA unchecked)
      expect(savedEntries[0].filters.sources).not.toContain('CA')
      expect(savedEntries[0].filters.sources).toEqual(
        expect.arrayContaining(['LS', 'RS'])
      )
    })
  })

  it('saved cookie is written without an expiry option (persistent)', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse({ results: [makeSpeechResult()] }),
    })
    renderResults('/search?q=budget+session&page=1')
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-bookmark-btn'))
    await screen.findByTestId('saved-searches-panel')
    // Saving writes writeCookie(SAVED_COOKIE, data) with no options arg (Gap 6)
    fireEvent.click(screen.getByTestId('saved-search-save-btn'))

    await waitFor(() => {
      const savedCalls = cookieModule.writeCookie.mock.calls.filter(
        (c) => c[0] === 'ss_saved'
      )
      expect(savedCalls.length).toBeGreaterThan(0)
      // Exactly 2 arguments (name + data); no third options/expiry argument
      expect(savedCalls[savedCalls.length - 1]).toHaveLength(2)
    })
  })
})

// ── F10 Debug mode ────────────────────────────────────────────────────────────

describe('Results — debug mode activation (?debug=1)', () => {
  function makeDebugResult(overrides = {}) {
    return {
      ...makeSpeechResult({ id: 'debug-res-1' }),
      _rankingScore: 0.87,
      _meili_document: { id: 'debug-res-1', source: 'LS' },
      ...overrides,
    }
  }

  function makeDebugSearchResponse(overrides = {}) {
    return {
      ...makeSearchResponse({ results: [makeDebugResult()] }),
      debug: {
        processed_query: 'rights',
        meilisearch_request: {
          method: 'POST',
          url: 'https://xxx.meilisearch.io/indexes/parliamentary_records/search',
          body: { q: 'rights', showRankingScore: true },
        },
        meilisearch_response: { hits: [{ id: 'debug-res-1' }], totalHits: 1 },
      },
      ...overrides,
    }
  }

  it('renders SearchDebugPanel above results when ?debug=1 is in URL', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeDebugSearchResponse(),
    })
    renderResults('/search?q=rights&page=1&debug=1')
    await screen.findByTestId('results-list')
    expect(screen.getByTestId('search-debug-panel')).toBeInTheDocument()
  })

  it('renders SearchDebugPanel when ?debug=true is in URL', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeDebugSearchResponse(),
    })
    renderResults('/search?q=rights&page=1&debug=true')
    await screen.findByTestId('results-list')
    expect(screen.getByTestId('search-debug-panel')).toBeInTheDocument()
  })

  it('does NOT render SearchDebugPanel in normal mode (no ?debug param)', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse(),
    })
    renderResults('/search?q=rights&page=1')
    await screen.findByTestId('results-list')
    expect(screen.queryByTestId('search-debug-panel')).not.toBeInTheDocument()
  })

  it('each ResultCard shows a debug-panel-toggle in debug mode', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeDebugSearchResponse(),
    })
    renderResults('/search?q=rights&page=1&debug=1')
    await screen.findByTestId('results-list')
    const toggles = screen.getAllByTestId('debug-panel-toggle')
    expect(toggles.length).toBeGreaterThan(0)
  })

  it('ResultCard has no debug-panel-toggle in normal mode', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse({ results: [makeSpeechResult()] }),
    })
    renderResults('/search?q=rights&page=1')
    await screen.findByTestId('results-list')
    expect(screen.queryByTestId('debug-panel-toggle')).not.toBeInTheDocument()
  })

  it('no calls to /api/debug/* when debug mode is inactive', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse(),
    })
    renderResults('/search?q=rights&page=1')
    await screen.findByTestId('results-list')
    const debugCalls = global.fetch.mock.calls.filter(([url]) =>
      typeof url === 'string' && url.includes('/api/debug/')
    )
    expect(debugCalls).toHaveLength(0)
  })

  it('POSTs to /api/search?debug=1 when ?debug=1 is in the URL', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse(),
    })
    renderResults('/search?q=rights&page=1&debug=1')
    await screen.findByTestId('results-list')
    const searchCalls = global.fetch.mock.calls.filter(([url]) =>
      typeof url === 'string' && url.includes('/api/search')
    )
    expect(searchCalls.length).toBeGreaterThan(0)
    expect(searchCalls[0][0]).toBe('/api/search?debug=1')
  })

  it('POSTs to plain /api/search when no debug param is present', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeSearchResponse(),
    })
    renderResults('/search?q=rights&page=1')
    await screen.findByTestId('results-list')
    const searchCalls = global.fetch.mock.calls.filter(([url]) =>
      typeof url === 'string' && url.includes('/api/search')
    )
    expect(searchCalls.length).toBeGreaterThan(0)
    expect(searchCalls[0][0]).toBe('/api/search')
  })
})
