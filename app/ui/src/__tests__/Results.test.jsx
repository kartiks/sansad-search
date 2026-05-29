import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

import Results from '../pages/Results.jsx'
import {
  makeSearchResponse,
  makeSpeechResult,
  makeQAResult,
} from './fixtures.js'

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
  global.fetch = vi.fn()
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
    expect(screen.getByTestId('advanced-search-modal')).toBeInTheDocument()
  })

  it('modal close button closes the modal', async () => {
    renderResults()
    await screen.findByTestId('results-list')
    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    expect(screen.getByTestId('advanced-search-modal')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('modal-close'))
    expect(screen.queryByTestId('advanced-search-modal')).toBeNull()
  })

  it('applying a body filter via modal shows a filter chip', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    // Uncheck CA — leaving LS and RS
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
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
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      const calls = global.fetch.mock.calls
      const lastBody = JSON.parse(calls[calls.length - 1][1].body)
      expect(lastBody.filters).toBeDefined()
      expect(lastBody.filters.sources).toEqual(expect.arrayContaining(['LS', 'RS']))
      expect(lastBody.filters.sources).not.toContain('CA')
    })
  })

  it('chip × removes the filter and re-fetches without it', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    // Apply a source filter
    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })

    // Remove via chip ×
    const removeBtn = screen.getByTestId('filter-chip-remove')
    fireEvent.click(removeBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('filter-chips-row')).toBeNull()
    })

    // Last request should have no sources filter
    const calls = global.fetch.mock.calls
    const lastBody = JSON.parse(calls[calls.length - 1][1].body)
    expect(lastBody.filters?.sources).toBeUndefined()
  })

  it('"Clear all" chips link resets all filters', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
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

    // Apply RS-only filter
    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })

    // Refine the query
    const input = screen.getByTestId('results-search-input')
    fireEvent.change(input, { target: { value: 'new query' } })
    fireEvent.click(screen.getByTestId('results-search-submit'))

    // Chips row should still be visible
    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })

    // Last request should still carry the filter
    await waitFor(() => {
      const calls = global.fetch.mock.calls
      const lastBody = JSON.parse(calls[calls.length - 1][1].body)
      expect(lastBody.filters?.sources).toEqual(['RS'])
    })
  })

  it('zero-selection validation: all bodies unchecked shows validation, no search', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    const fetchCallsBefore = global.fetch.mock.calls.length

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
    fireEvent.click(screen.getByTestId('source-checkbox-RS'))

    // Apply should be disabled — clicking should not call fetch
    const applyBtn = screen.getByTestId('modal-apply')
    expect(applyBtn).toBeDisabled()
    fireEvent.click(applyBtn)

    // Fetch call count should not increase
    expect(global.fetch.mock.calls.length).toBe(fetchCallsBefore)
    expect(screen.getByTestId('source-validation')).toBeInTheDocument()
  })

  it('date validation: From > To shows error, Apply disabled', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
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

  it('modal pre-populates from active filter state when reopened', async () => {
    renderResults()
    await screen.findByTestId('results-list')

    // Apply RS-only filter
    fireEvent.click(screen.getByTestId('results-advanced-search-link'))
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
    fireEvent.click(screen.getByTestId('modal-apply'))

    await waitFor(() => {
      expect(screen.getByTestId('filter-chips-row')).toBeInTheDocument()
    })

    // Reopen modal
    fireEvent.click(screen.getByTestId('results-advanced-search-link'))

    expect(screen.getByTestId('source-checkbox-CA')).not.toBeChecked()
    expect(screen.getByTestId('source-checkbox-LS')).not.toBeChecked()
    expect(screen.getByTestId('source-checkbox-RS')).toBeChecked()
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
