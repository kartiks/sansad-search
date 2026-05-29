import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import IndexingStatusPage from '../pages/IndexingStatusPage.jsx'
import { makeStatusResponse } from './fixtures.js'

function renderPage() {
  return render(
    <MemoryRouter>
      <IndexingStatusPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  global.fetch = vi.fn()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('IndexingStatusPage — loaded data', () => {
  it('renders the "Search Index Status" header', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    renderPage()
    expect(
      await screen.findByText('Search Index Status')
    ).toBeInTheDocument()
  })

  it('reads from GET /api/status (not a live index query)', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    renderPage()
    await screen.findByTestId('status-panel')
    expect(global.fetch).toHaveBeenCalledWith('/api/status')
  })

  it('renders total records with thousands separators', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    renderPage()
    const total = await screen.findByTestId('status-panel-total')
    expect(total.textContent).toContain('Total records indexed: 350,000')
  })

  it('renders per-source counts and date coverage for each body', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    renderPage()
    await screen.findByTestId('status-panel-table')

    const ca = screen.getByTestId('status-row-ca')
    expect(ca.textContent).toContain('Constituent Assembly')
    expect(ca.textContent).toContain('8,200 records')
    expect(ca.textContent).toContain('Dec 1946 – Nov 1950')

    const ls = screen.getByTestId('status-row-ls')
    expect(ls.textContent).toContain('Lok Sabha')
    expect(ls.textContent).toContain('198,000 records')
    expect(ls.textContent).toContain('Jun 2014 – May 2026')

    const rs = screen.getByTestId('status-row-rs')
    expect(rs.textContent).toContain('Rajya Sabha')
    expect(rs.textContent).toContain('143,800 records')
    expect(rs.textContent).toContain('Jun 2014 – Apr 2026')
  })

  it('renders "Last updated" as DD Month YYYY from the ingestion timestamp', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    renderPage()
    const updated = await screen.findByTestId('status-panel-updated')
    expect(updated.textContent).toContain('Last updated: 15 May 2026')
  })

  it('displays a total equal to the sum of the three per-source counts', async () => {
    const ca = 1000
    const ls = 2000
    const rs = 3000
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeStatusResponse({
          total_records: ca + ls + rs,
          sources: {
            ca: { count: ca, date_from: '1946-12-09', date_to: '1950-11-26' },
            ls: { count: ls, date_from: '2014-06-04', date_to: '2026-05-15' },
            rs: { count: rs, date_from: '2014-06-11', date_to: '2026-04-20' },
          },
        }),
    })
    renderPage()
    const total = await screen.findByTestId('status-panel-total')
    expect(total.textContent).toContain('6,000')
  })
})

describe('IndexingStatusPage — zero-source and fresh-deploy states', () => {
  it('shows "0 records – not yet indexed" with no date range for a zero-count source', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeStatusResponse({
          sources: {
            ca: { count: 0, date_from: null, date_to: null },
            ls: { count: 198000, date_from: '2014-06-04', date_to: '2026-05-15' },
            rs: { count: 143800, date_from: '2014-06-11', date_to: '2026-04-20' },
          },
        }),
    })
    renderPage()
    await screen.findByTestId('status-panel-table')
    const ca = screen.getByTestId('status-row-ca')
    expect(ca.textContent).toContain('0 records – not yet indexed')
    // No date range, no placeholder date, no "records" count for the zero row
    expect(ca.textContent).not.toContain('1970')
    expect(ca.textContent).not.toMatch(/\d{4} – \d{4}|\w{3} \d{4} –/)
  })

  it('fresh deploy: all sources "0 records – not yet indexed" and "Last updated: Never"', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () =>
        makeStatusResponse({
          total_records: 0,
          sources: {
            ca: { count: 0, date_from: null, date_to: null },
            ls: { count: 0, date_from: null, date_to: null },
            rs: { count: 0, date_from: null, date_to: null },
          },
          last_updated: null,
        }),
    })
    renderPage()
    await screen.findByTestId('status-panel-table')
    for (const key of ['ca', 'ls', 'rs']) {
      expect(screen.getByTestId(`status-row-${key}`).textContent).toContain(
        '0 records – not yet indexed'
      )
    }
    expect(screen.getByTestId('status-panel-updated').textContent).toContain(
      'Last updated: Never'
    )
    expect(screen.getByTestId('status-panel-total').textContent).toContain(
      'Total records indexed: 0'
    )
  })
})

describe('IndexingStatusPage — unavailable states', () => {
  it('shows "Status unavailable" when the API returns status=unavailable', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'unavailable' }),
    })
    renderPage()
    expect(
      await screen.findByTestId('status-panel-unavailable')
    ).toHaveTextContent('Status unavailable')
    // Counts/dates must not render in the unavailable state
    expect(screen.queryByTestId('status-panel-total')).toBeNull()
    expect(screen.queryByTestId('status-panel-table')).toBeNull()
  })

  it('shows "Status unavailable" when the status fetch fails', async () => {
    global.fetch.mockRejectedValue(new Error('network down'))
    renderPage()
    expect(
      await screen.findByTestId('status-panel-unavailable')
    ).toHaveTextContent('Status unavailable')
    expect(screen.queryByTestId('status-panel')).toBeNull()
  })

  it('shows "Status unavailable" when the payload is malformed (missing sources)', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', total_records: 5 }),
    })
    renderPage()
    expect(
      await screen.findByTestId('status-panel-unavailable')
    ).toBeInTheDocument()
  })
})
