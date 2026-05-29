import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Pagination, {
  formatResultCount,
  buildPageList,
  MAX_TOTAL_PAGE_COUNT_DISPLAY,
} from '../components/Pagination.jsx'

describe('formatResultCount (F05)', () => {
  it('returns exact count for <= 9,999 results', () => {
    expect(formatResultCount(0)).toBe('0 results')
    expect(formatResultCount(1)).toBe('1 results')
    expect(formatResultCount(47)).toBe('47 results')
    expect(formatResultCount(3241)).toBe('3,241 results')
    expect(formatResultCount(9999)).toBe('9,999 results')
  })

  it('returns "10,000+ results" exactly at 10,000', () => {
    expect(formatResultCount(10000)).toBe('10,000+ results')
  })

  it('returns "10,000+ results" above 10,000', () => {
    expect(formatResultCount(50000)).toBe('10,000+ results')
    expect(formatResultCount(1000000)).toBe('10,000+ results')
  })

  it('returns "0 results" for zero', () => {
    expect(formatResultCount(0)).toBe('0 results')
  })

  it('handles null/undefined', () => {
    expect(formatResultCount(null)).toBe('')
    expect(formatResultCount(undefined)).toBe('')
  })
})

describe('buildPageList', () => {
  it('returns just the single page when total is 1', () => {
    expect(buildPageList(1, 1)).toEqual([1])
  })

  it('includes first, last, current and adjacent', () => {
    expect(buildPageList(5, 10)).toEqual([1, '…', 4, 5, 6, '…', 10])
  })

  it('does not insert an ellipsis when pages are adjacent', () => {
    expect(buildPageList(2, 3)).toEqual([1, 2, 3])
  })
})

describe('Pagination component', () => {
  it('returns null when only one page', () => {
    const { container } = render(
      <Pagination currentPage={1} totalPages={1} onPageChange={() => {}} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders Previous and Next', () => {
    render(
      <Pagination currentPage={3} totalPages={10} onPageChange={() => {}} />
    )
    expect(screen.getByLabelText('Previous page')).toBeInTheDocument()
    expect(screen.getByLabelText('Next page')).toBeInTheDocument()
  })

  it('disables Previous on page 1', () => {
    render(
      <Pagination currentPage={1} totalPages={5} onPageChange={() => {}} />
    )
    expect(screen.getByLabelText('Previous page')).toBeDisabled()
  })

  it('disables Next on the last page', () => {
    render(
      <Pagination currentPage={5} totalPages={5} onPageChange={() => {}} />
    )
    expect(screen.getByLabelText('Next page')).toBeDisabled()
  })

  it('marks the current page as is-current', () => {
    render(
      <Pagination currentPage={3} totalPages={5} onPageChange={() => {}} />
    )
    const current = screen.getByText('3')
    expect(current).toHaveClass('is-current')
    expect(current).toHaveAttribute('aria-current', 'page')
  })

  it('calls onPageChange with the chosen page', () => {
    const onPageChange = vi.fn()
    render(
      <Pagination currentPage={3} totalPages={5} onPageChange={onPageChange} />
    )
    fireEvent.click(screen.getByText('4'))
    expect(onPageChange).toHaveBeenCalledWith(4)
  })

  it('Next button advances by one', () => {
    const onPageChange = vi.fn()
    render(
      <Pagination currentPage={3} totalPages={5} onPageChange={onPageChange} />
    )
    fireEvent.click(screen.getByLabelText('Next page'))
    expect(onPageChange).toHaveBeenCalledWith(4)
  })

  it('Previous button goes back by one', () => {
    const onPageChange = vi.fn()
    render(
      <Pagination currentPage={3} totalPages={5} onPageChange={onPageChange} />
    )
    fireEvent.click(screen.getByLabelText('Previous page'))
    expect(onPageChange).toHaveBeenCalledWith(2)
  })

  it('hides total page hint when above the 500 threshold', () => {
    render(
      <Pagination
        currentPage={1}
        totalPages={MAX_TOTAL_PAGE_COUNT_DISPLAY + 100}
        onPageChange={() => {}}
      />
    )
    expect(screen.queryByTestId('total-pages-hint')).toBeNull()
  })

  it('shows total page hint when within the threshold', () => {
    render(
      <Pagination currentPage={1} totalPages={50} onPageChange={() => {}} />
    )
    expect(screen.getByTestId('total-pages-hint')).toBeInTheDocument()
  })
})
