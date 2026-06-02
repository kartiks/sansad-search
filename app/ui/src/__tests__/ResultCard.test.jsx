import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ResultCard from '../components/ResultCard.jsx'
import { makeSpeechResult, makeQAResult } from './fixtures.js'

function renderCard(result) {
  return render(
    <MemoryRouter>
      <ResultCard result={result} />
    </MemoryRouter>
  )
}

describe('ResultCard — dispatcher', () => {
  it('renders SpeechCard for record_type=speech', () => {
    renderCard(makeSpeechResult())
    expect(screen.getByTestId('speech-card')).toBeInTheDocument()
    expect(screen.queryByTestId('qa-card')).toBeNull()
  })

  it('renders QACard for record_type=qa', () => {
    renderCard(makeQAResult())
    expect(screen.getByTestId('qa-card')).toBeInTheDocument()
    expect(screen.queryByTestId('speech-card')).toBeNull()
  })

  it('renders nothing for null', () => {
    const { container } = renderCard(null)
    expect(container.firstChild).toBeNull()
  })
})

describe('ResultCard — links to /record/:id', () => {
  it('speech card is wrapped in a link to /record/:id', () => {
    renderCard(makeSpeechResult({ id: 'speech-1' }))
    const card = screen.getByTestId('speech-card')
    expect(card.closest('a')).toHaveAttribute('href', '/record/speech-1')
  })

  it('qa card is wrapped in a link to /record/:id', () => {
    renderCard(makeQAResult({ id: 'qa-1' }))
    const card = screen.getByTestId('qa-card')
    expect(card.closest('a')).toHaveAttribute('href', '/record/qa-1')
  })

  it('link href uses the result id field', () => {
    renderCard(makeSpeechResult({ id: 'custom-id-xyz' }))
    const card = screen.getByTestId('speech-card')
    expect(card.closest('a')).toHaveAttribute('href', '/record/custom-id-xyz')
  })
})
