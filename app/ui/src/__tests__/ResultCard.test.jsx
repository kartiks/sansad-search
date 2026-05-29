import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ResultCard from '../components/ResultCard.jsx'
import { makeSpeechResult, makeQAResult } from './fixtures.js'

describe('ResultCard — dispatcher', () => {
  it('renders SpeechCard for record_type=speech', () => {
    render(<ResultCard result={makeSpeechResult()} />)
    expect(screen.getByTestId('speech-card')).toBeInTheDocument()
    expect(screen.queryByTestId('qa-card')).toBeNull()
  })

  it('renders QACard for record_type=qa', () => {
    render(<ResultCard result={makeQAResult()} />)
    expect(screen.getByTestId('qa-card')).toBeInTheDocument()
    expect(screen.queryByTestId('speech-card')).toBeNull()
  })

  it('renders nothing for null', () => {
    const { container } = render(<ResultCard result={null} />)
    expect(container.firstChild).toBeNull()
  })
})
