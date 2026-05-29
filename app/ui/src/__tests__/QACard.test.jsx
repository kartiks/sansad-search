import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import QACard, { formatQuestionerNames } from '../components/QACard.jsx'
import { makeQAResult } from './fixtures.js'

describe('formatQuestionerNames', () => {
  it('no label for exactly one questioner', () => {
    expect(formatQuestionerNames(['Shri A'])).toBe('Shri A')
  })

  it('"+3 others" for 4 total (1 primary + 3 co-sigs)', () => {
    expect(formatQuestionerNames(['A', 'B', 'C', 'D'])).toBe('A +3 others')
  })

  it('returns empty string for empty / non-array input', () => {
    expect(formatQuestionerNames([])).toBe('')
    expect(formatQuestionerNames(null)).toBe('')
    expect(formatQuestionerNames(undefined)).toBe('')
  })
})

describe('QACard — base rendering', () => {
  it('renders the metadata row', () => {
    render(<QACard result={makeQAResult()} />)
    expect(screen.getByText('Starred Question')).toBeInTheDocument()
    expect(screen.getByText('Lok Sabha')).toBeInTheDocument()
    expect(screen.getByText('4 August 2023')).toBeInTheDocument()
    expect(screen.getByText('Monsoon Session 2023')).toBeInTheDocument()
  })

  it('renders subject', () => {
    render(<QACard result={makeQAResult()} />)
    expect(
      screen.getByText('Implementation of National Health Mission')
    ).toBeInTheDocument()
  })

  it('renders question number prefixed with "Q."', () => {
    render(<QACard result={makeQAResult()} />)
    expect(screen.getByTestId('question-number')).toHaveTextContent('Q. 42')
  })

  it('renders the questioner row with party', () => {
    render(<QACard result={makeQAResult()} />)
    const row = screen.getByTestId('questioner-row')
    expect(row).toHaveTextContent('Shri A. Kumar')
    expect(row).toHaveTextContent('BJP')
  })

  it('renders minister and ministry on a single line', () => {
    render(<QACard result={makeQAResult()} />)
    expect(screen.getByTestId('minister-row')).toHaveTextContent(
      'Answered by Dr. Mansukh Mandaviya, Ministry of Health and Family Welfare'
    )
  })

  it('renders the snippet', () => {
    render(<QACard result={makeQAResult()} />)
    expect(screen.getByTestId('snippet')).toBeInTheDocument()
  })

  it('renders View source link', () => {
    render(<QACard result={makeQAResult()} />)
    expect(screen.getByText('View source ↗')).toHaveAttribute(
      'href',
      'https://sansad.in/qa-example'
    )
  })
})

describe('QACard — co-signatory display', () => {
  it('1 questioner shows no "+N others" label', () => {
    render(<QACard result={makeQAResult({ questioner_names: ['Shri A'] })} />)
    expect(screen.getByTestId('questioner-row')).toHaveTextContent('Shri A')
    expect(screen.queryByText(/others/)).toBeNull()
  })

  it('3 co-signatories (4 total) shows "+3 others"', () => {
    render(
      <QACard
        result={makeQAResult({ questioner_names: ['A', 'B', 'C', 'D'] })}
      />
    )
    expect(screen.getByTestId('questioner-row')).toHaveTextContent('+3 others')
  })
})

describe('QACard — supplementary exchange prefix', () => {
  it('renders "From supplementary exchange — " prefix when flag set', () => {
    render(
      <QACard result={makeQAResult({ snippet_from_supplementary: true })} />
    )
    expect(screen.getByTestId('supplementary-prefix')).toHaveTextContent(
      'From supplementary exchange —'
    )
  })

  it('omits the prefix when flag is false', () => {
    render(
      <QACard result={makeQAResult({ snippet_from_supplementary: false })} />
    )
    expect(screen.queryByTestId('supplementary-prefix')).toBeNull()
  })
})

describe('QACard — edge cases', () => {
  it('renders untranslated placeholder when snippet is null', () => {
    render(<QACard result={makeQAResult({ snippet: null })} />)
    expect(screen.getByTestId('untranslated-placeholder')).toBeInTheDocument()
  })

  it('still shows metadata when snippet is null', () => {
    render(<QACard result={makeQAResult({ snippet: null })} />)
    expect(screen.getByText('Starred Question')).toBeInTheDocument()
    expect(screen.getByText('Lok Sabha')).toBeInTheDocument()
  })

  it('shows "Translated from Hindi" when is_translated true', () => {
    render(<QACard result={makeQAResult({ is_translated: true })} />)
    expect(screen.getByText('Translated from Hindi')).toBeInTheDocument()
  })

  it('omits View source when source_url is null', () => {
    render(<QACard result={makeQAResult({ source_url: null })} />)
    expect(screen.queryByText('View source ↗')).toBeNull()
  })

  it('omits questioner_party when not provided', () => {
    render(
      <QACard result={makeQAResult({ questioner_party: null })} />
    )
    expect(screen.queryByText(/BJP/)).toBeNull()
  })

  it('renders RAW HTML in snippet as literal text — script/img do not become live elements', () => {
    // Unescaped hostile payload fed straight into the card.
    const hostile =
      '<script>alert(1)</script><img src=x onerror="alert(2)"> The <mark>NHM</mark> covers all states.'
    const { container } = render(
      <QACard result={makeQAResult({ snippet: hostile })} />
    )
    const snippet = container.querySelector('[data-testid="snippet-text"]')
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(snippet.textContent).toContain('<script>alert(1)</script>')
    expect(snippet.textContent).toContain('<img src=x onerror="alert(2)">')
    // Legitimate highlight preserved
    expect(snippet.querySelector('mark')).not.toBeNull()
    expect(snippet.querySelector('mark').textContent).toBe('NHM')
  })
})
