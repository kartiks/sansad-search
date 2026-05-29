import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SkeletonCard from '../components/SkeletonCard.jsx'

describe('SkeletonCard', () => {
  it('renders shimmer blocks', () => {
    const { container } = render(<SkeletonCard />)
    const blocks = container.querySelectorAll('.skeleton-block')
    expect(blocks.length).toBeGreaterThanOrEqual(4)
  })

  it('is aria-hidden so screen readers skip it', () => {
    render(<SkeletonCard />)
    expect(screen.getByTestId('skeleton-card')).toHaveAttribute(
      'aria-hidden',
      'true'
    )
  })
})
