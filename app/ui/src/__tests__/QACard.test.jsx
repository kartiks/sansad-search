import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import QACard, { formatQuestionerNames } from '../components/QACard.jsx'
import { makeQAResult } from './fixtures.js'

const DETAIL_TO = '/record/test-qa-id'
const DETAIL_STATE = { from: 'search', resultsPath: '/results?q=test', filters: null }

function renderCard(result, props = {}) {
  return render(
    <MemoryRouter>
      <QACard
        result={result}
        detailTo={DETAIL_TO}
        detailState={DETAIL_STATE}
        {...props}
      />
    </MemoryRouter>
  )
}

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
    renderCard(makeQAResult())
    expect(screen.getByText('Starred Question')).toBeInTheDocument()
    expect(screen.getByText('Lok Sabha')).toBeInTheDocument()
    expect(screen.getByText('4 August 2023')).toBeInTheDocument()
    expect(screen.getByText('Monsoon Session 2023')).toBeInTheDocument()
  })

  it('renders subject', () => {
    renderCard(makeQAResult())
    expect(
      screen.getByText('Implementation of National Health Mission')
    ).toBeInTheDocument()
  })

  it('renders question number prefixed with "Q."', () => {
    renderCard(makeQAResult())
    expect(screen.getByTestId('question-number')).toHaveTextContent('Q. 42')
  })

  it('renders the questioner row with party', () => {
    renderCard(makeQAResult())
    const row = screen.getByTestId('questioner-row')
    expect(row).toHaveTextContent('Shri A. Kumar')
    expect(row).toHaveTextContent('BJP')
  })

  it('renders minister and ministry on a single line', () => {
    renderCard(makeQAResult())
    expect(screen.getByTestId('minister-row')).toHaveTextContent(
      'Answered by Dr. Mansukh Mandaviya, Ministry of Health and Family Welfare'
    )
  })

  it('renders the snippet', () => {
    renderCard(makeQAResult())
    expect(screen.getByTestId('snippet')).toBeInTheDocument()
  })

  it('renders View source link', () => {
    renderCard(makeQAResult())
    expect(screen.getByText('View source ↗')).toHaveAttribute(
      'href',
      'https://sansad.in/qa-example'
    )
  })
})

describe('QACard — detail links', () => {
  it('subject is a link to the detail page', () => {
    renderCard(makeQAResult())
    const link = screen.getByTestId('subject-detail-link')
    expect(link).toHaveAttribute('href', DETAIL_TO)
    expect(link).toHaveTextContent('Implementation of National Health Mission')
  })

  it('question number is a link to the detail page', () => {
    renderCard(makeQAResult())
    const link = screen.getByTestId('question-number-link')
    expect(link).toHaveAttribute('href', DETAIL_TO)
    expect(link).toHaveTextContent('Q. 42')
  })

  it('questioner name is a link to the detail page', () => {
    renderCard(makeQAResult())
    const link = screen.getByTestId('questioner-detail-link')
    expect(link).toHaveAttribute('href', DETAIL_TO)
    expect(link).toHaveTextContent('Shri A. Kumar')
  })

  it('questioner party stays as plain text outside the link', () => {
    renderCard(makeQAResult())
    const link = screen.getByTestId('questioner-detail-link')
    expect(link).not.toHaveTextContent('BJP')
    expect(screen.getByTestId('questioner-row')).toHaveTextContent('BJP')
  })

  it('minister row is a link to the detail page', () => {
    renderCard(makeQAResult())
    const link = screen.getByTestId('minister-detail-link')
    expect(link).toHaveAttribute('href', DETAIL_TO)
    expect(link).toHaveTextContent('Answered by Dr. Mansukh Mandaviya')
  })

  it('Details link is present and points to the detail page', () => {
    renderCard(makeQAResult())
    const link = screen.getByTestId('details-link')
    expect(link).toHaveAttribute('href', DETAIL_TO)
    expect(link).toHaveTextContent('Details')
  })

  it('omits subject link when subject is null', () => {
    renderCard(makeQAResult({ subject: null }))
    expect(screen.queryByTestId('subject-detail-link')).toBeNull()
  })

  it('omits question-number link when question_number is null', () => {
    renderCard(makeQAResult({ question_number: null }))
    expect(screen.queryByTestId('question-number-link')).toBeNull()
  })

  it('omits questioner link when questioner_names is empty', () => {
    renderCard(makeQAResult({ questioner_names: [] }))
    expect(screen.queryByTestId('questioner-detail-link')).toBeNull()
  })

  it('omits minister link when minister_name and ministry are both null', () => {
    renderCard(makeQAResult({ minister_name: null, ministry: null }))
    expect(screen.queryByTestId('minister-detail-link')).toBeNull()
  })
})

describe('QACard — co-signatory display', () => {
  it('1 questioner shows no "+N others" label', () => {
    renderCard(makeQAResult({ questioner_names: ['Shri A'] }))
    expect(screen.getByTestId('questioner-row')).toHaveTextContent('Shri A')
    expect(screen.queryByText(/others/)).toBeNull()
  })

  it('3 co-signatories (4 total) shows "+3 others"', () => {
    renderCard(
      makeQAResult({ questioner_names: ['A', 'B', 'C', 'D'] })
    )
    expect(screen.getByTestId('questioner-row')).toHaveTextContent('+3 others')
  })
})

describe('QACard — supplementary exchange prefix', () => {
  it('renders "From supplementary exchange — " prefix when flag set', () => {
    renderCard(
      makeQAResult({ snippet_from_supplementary: true })
    )
    expect(screen.getByTestId('supplementary-prefix')).toHaveTextContent(
      'From supplementary exchange —'
    )
  })

  it('omits the prefix when flag is false', () => {
    renderCard(
      makeQAResult({ snippet_from_supplementary: false })
    )
    expect(screen.queryByTestId('supplementary-prefix')).toBeNull()
  })
})

describe('QACard — edge cases', () => {
  it('renders untranslated placeholder when snippet is null', () => {
    renderCard(makeQAResult({ snippet: null }))
    expect(screen.getByTestId('untranslated-placeholder')).toBeInTheDocument()
  })

  it('still shows metadata when snippet is null', () => {
    renderCard(makeQAResult({ snippet: null }))
    expect(screen.getByText('Starred Question')).toBeInTheDocument()
    expect(screen.getByText('Lok Sabha')).toBeInTheDocument()
  })

  it('shows "Translated from Hindi" when is_translated true', () => {
    renderCard(makeQAResult({ is_translated: true }))
    expect(screen.getByText('Translated from Hindi')).toBeInTheDocument()
  })

  it('omits View source when source_url is null', () => {
    renderCard(makeQAResult({ source_url: null }))
    expect(screen.queryByText('View source ↗')).toBeNull()
  })

  it('omits questioner_party when not provided', () => {
    renderCard(
      makeQAResult({ questioner_party: null })
    )
    expect(screen.queryByText(/BJP/)).toBeNull()
  })

  it('renders RAW HTML in snippet as literal text — script/img do not become live elements', () => {
    const hostile =
      '<script>alert(1)</script><img src=x onerror="alert(2)"> The <mark>NHM</mark> covers all states.'
    const { container } = renderCard(makeQAResult({ snippet: hostile }))
    const snippet = container.querySelector('[data-testid="snippet-text"]')
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(snippet.textContent).toContain('<script>alert(1)</script>')
    expect(snippet.textContent).toContain('<img src=x onerror="alert(2)">')
    expect(snippet.querySelector('mark')).not.toBeNull()
    expect(snippet.querySelector('mark').textContent).toBe('NHM')
  })
})

describe('QACard — F05 v2.0: lang_original badge', () => {
  it('renders "Hindi original" badge for lang_original=hi', () => {
    renderCard(makeQAResult({ lang_original: 'hi' }))
    expect(screen.getByTestId('lang-badge')).toHaveTextContent('Hindi original')
  })

  it('renders "Mixed language" badge for lang_original=mixed', () => {
    renderCard(makeQAResult({ lang_original: 'mixed' }))
    expect(screen.getByTestId('lang-badge')).toHaveTextContent('Mixed language')
  })

  it('renders no badge for lang_original=en — element absent from DOM', () => {
    renderCard(makeQAResult({ lang_original: 'en' }))
    expect(screen.queryByTestId('lang-badge')).toBeNull()
  })

  it('renders no badge when lang_original is null', () => {
    renderCard(makeQAResult({ lang_original: null }))
    expect(screen.queryByTestId('lang-badge')).toBeNull()
  })
})

describe('QACard — F05 v2.0: time_of_day', () => {
  it('renders time_of_day verbatim when present', () => {
    renderCard(makeQAResult({ time_of_day: '09:30' }))
    expect(screen.getByTestId('time-of-day')).toHaveTextContent('09:30')
  })

  it('renders no time element when time_of_day is null — element absent from DOM', () => {
    renderCard(makeQAResult({ time_of_day: null }))
    expect(screen.queryByTestId('time-of-day')).toBeNull()
  })
})
