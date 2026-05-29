import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import FilterChip from '../components/FilterChip.jsx'

function renderChip(label = 'Lok Sabha', onRemove = vi.fn()) {
  return { ...render(<FilterChip label={label} onRemove={onRemove} />), onRemove }
}

describe('FilterChip', () => {
  it('renders the chip label', () => {
    renderChip('Rajya Sabha')
    expect(screen.getByText('Rajya Sabha')).toBeInTheDocument()
  })

  it('renders the remove button', () => {
    renderChip()
    expect(screen.getByTestId('filter-chip-remove')).toBeInTheDocument()
  })

  it('remove button has descriptive aria-label', () => {
    renderChip('Lok Sabha')
    const btn = screen.getByTestId('filter-chip-remove')
    expect(btn).toHaveAttribute('aria-label', 'Remove filter: Lok Sabha')
  })

  it('clicking × calls onRemove', () => {
    const { onRemove } = renderChip()
    fireEvent.click(screen.getByTestId('filter-chip-remove'))
    expect(onRemove).toHaveBeenCalledOnce()
  })

  it('renders chip container with correct testid', () => {
    renderChip('Speaker: Ambedkar')
    expect(screen.getByTestId('filter-chip')).toBeInTheDocument()
  })
})
