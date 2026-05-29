import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import Toast, { TOAST_DEFAULT_MS } from '../components/Toast.jsx'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Toast', () => {
  it('renders the message', () => {
    render(<Toast message="Search saved" onDismiss={() => {}} />)
    expect(screen.getByText('Search saved')).toBeInTheDocument()
  })

  it('renders nothing when message is falsy', () => {
    const { container } = render(<Toast message="" onDismiss={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('auto-dismisses after 3 seconds by default', () => {
    const onDismiss = vi.fn()
    render(<Toast message="Hi" onDismiss={onDismiss} />)
    expect(onDismiss).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(TOAST_DEFAULT_MS)
    })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('honours a custom duration', () => {
    const onDismiss = vi.fn()
    render(<Toast message="Hi" durationMs={1000} onDismiss={onDismiss} />)
    act(() => {
      vi.advanceTimersByTime(999)
    })
    expect(onDismiss).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(onDismiss).toHaveBeenCalled()
  })

  it('uses an accessible role for screen readers', () => {
    render(<Toast message="Saved" onDismiss={() => {}} />)
    expect(screen.getByRole('status')).toHaveTextContent('Saved')
  })
})
