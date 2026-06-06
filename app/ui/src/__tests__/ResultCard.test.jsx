import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import ResultCard from '../components/ResultCard.jsx'
import { makeSpeechResult, makeQAResult } from './fixtures.js'

function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

function renderCard(result) {
  return render(
    <MemoryRouter>
      <ResultCard result={result} />
    </MemoryRouter>
  )
}

function renderCardWithRouter(result) {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<ResultCard result={result} />} />
        <Route path="/record/:id" element={<LocationDisplay />} />
      </Routes>
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

describe('ResultCard — card wrapper is not itself a link', () => {
  it('speech card is not wrapped in an anchor element', () => {
    renderCard(makeSpeechResult({ id: 'speech-1' }))
    const card = screen.getByTestId('speech-card')
    expect(card.closest('a')).toBeNull()
  })

  it('qa card is not wrapped in an anchor element', () => {
    renderCard(makeQAResult({ id: 'qa-1' }))
    const card = screen.getByTestId('qa-card')
    expect(card.closest('a')).toBeNull()
  })
})

describe('ResultCard — Details link navigates to /record/:id', () => {
  it('Details link on speech card navigates to /record/:id', () => {
    renderCardWithRouter(makeSpeechResult({ id: 'speech-1' }))
    fireEvent.click(screen.getByTestId('details-link'))
    expect(screen.getByTestId('location')).toHaveTextContent('/record/speech-1')
  })

  it('Details link on qa card navigates to /record/:id', () => {
    renderCardWithRouter(makeQAResult({ id: 'qa-1' }))
    fireEvent.click(screen.getByTestId('details-link'))
    expect(screen.getByTestId('location')).toHaveTextContent('/record/qa-1')
  })

  it('Details link uses the result id field', () => {
    renderCardWithRouter(makeSpeechResult({ id: 'custom-id-xyz' }))
    fireEvent.click(screen.getByTestId('details-link'))
    expect(screen.getByTestId('location')).toHaveTextContent('/record/custom-id-xyz')
  })
})
