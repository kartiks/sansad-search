import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import SpeechCard from '../components/SpeechCard.jsx'
import { makeSpeechResult } from './fixtures.js'

const DETAIL_TO = '/record/test-speech-id'
const DETAIL_STATE = { from: 'search', resultsPath: '/results?q=test', filters: null }

function renderCard(result, props = {}) {
  return render(
    <MemoryRouter>
      <SpeechCard
        result={result}
        detailTo={DETAIL_TO}
        detailState={DETAIL_STATE}
        {...props}
      />
    </MemoryRouter>
  )
}

describe('SpeechCard — base rendering', () => {
  it('renders metadata row with proceeding badge, body, date, session', () => {
    renderCard(makeSpeechResult())
    expect(screen.getByText('Debate')).toBeInTheDocument()
    expect(screen.getByText('Lok Sabha')).toBeInTheDocument()
    expect(screen.getByText('15 March 2023')).toBeInTheDocument()
    expect(screen.getByText('Budget Session 2023')).toBeInTheDocument()
  })

  it('renders the speaker name', () => {
    renderCard(makeSpeechResult())
    expect(screen.getByText(/Jairam Ramesh/)).toBeInTheDocument()
  })

  it('renders the subject line', () => {
    renderCard(makeSpeechResult())
    expect(
      screen.getByText('General Discussion on the Union Budget')
    ).toBeInTheDocument()
  })

  it('renders the snippet with mark highlights', () => {
    renderCard(makeSpeechResult())
    const snippet = screen.getByTestId('snippet')
    expect(snippet.innerHTML).toContain('<mark>PM</mark>')
  })

  it('renders View source link with new-tab attributes', () => {
    renderCard(makeSpeechResult())
    const link = screen.getByText('View source ↗')
    expect(link).toHaveAttribute('href', 'https://sansad.in/example')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })
})

describe('SpeechCard — detail links', () => {
  it('speaker name is a link to the detail page', () => {
    renderCard(makeSpeechResult())
    const link = screen.getByTestId('speaker-detail-link')
    expect(link).toHaveAttribute('href', DETAIL_TO)
    expect(link).toHaveTextContent('Jairam Ramesh')
  })

  it('subject is a link to the detail page', () => {
    renderCard(makeSpeechResult())
    const link = screen.getByTestId('subject-detail-link')
    expect(link).toHaveAttribute('href', DETAIL_TO)
    expect(link).toHaveTextContent('General Discussion on the Union Budget')
  })

  it('Details link is present and points to the detail page', () => {
    renderCard(makeSpeechResult())
    const link = screen.getByTestId('details-link')
    expect(link).toHaveAttribute('href', DETAIL_TO)
    expect(link).toHaveTextContent('Details')
  })

  it('shows "Speaker unknown" as plain text (no link) when speaker_name is null', () => {
    renderCard(makeSpeechResult({ speaker_name: null }))
    expect(screen.getByText('Speaker unknown')).toBeInTheDocument()
    expect(screen.queryByTestId('speaker-detail-link')).toBeNull()
  })

  it('omits subject link when subject is null', () => {
    renderCard(makeSpeechResult({ subject: null }))
    expect(screen.queryByTestId('subject-detail-link')).toBeNull()
  })
})

describe('SpeechCard — F05 edge cases', () => {
  it('shows "Speaker unknown" when speaker_name is null', () => {
    renderCard(
      makeSpeechResult({ speaker_name: null, speaker_party: null, speaker_constituency_or_state: null })
    )
    expect(screen.getByText('Speaker unknown')).toBeInTheDocument()
  })

  it('omits party and constituency when both absent (no placeholder)', () => {
    renderCard(
      makeSpeechResult({ speaker_party: null, speaker_constituency_or_state: null })
    )
    expect(screen.queryByText(/INC/)).toBeNull()
    expect(screen.queryByText(/Karnataka/)).toBeNull()
  })

  it('shows party alone when constituency is missing', () => {
    renderCard(
      makeSpeechResult({ speaker_constituency_or_state: null })
    )
    expect(screen.getByText(/INC/)).toBeInTheDocument()
    expect(screen.queryByText(/Karnataka/)).toBeNull()
  })

  it('renders untranslated placeholder when snippet field is missing', () => {
    renderCard(
      makeSpeechResult({ snippet: undefined, snippet_from_supplementary: undefined })
    )
    expect(
      screen.getByText('This speech was delivered in Hindi. No English text is available.')
    ).toBeInTheDocument()
  })

  it('renders untranslated placeholder when snippet is explicitly null', () => {
    renderCard(makeSpeechResult({ snippet: null }))
    expect(screen.getByTestId('untranslated-placeholder')).toBeInTheDocument()
  })

  it('still shows all metadata for untranslated speech', () => {
    renderCard(makeSpeechResult({ snippet: null }))
    expect(screen.getByText('Debate')).toBeInTheDocument()
    expect(screen.getByText('Lok Sabha')).toBeInTheDocument()
    expect(screen.getByText('15 March 2023')).toBeInTheDocument()
    expect(screen.getByText('Jairam Ramesh')).toBeInTheDocument()
  })

  it('shows "Translated from Hindi" indicator when is_translated is true', () => {
    renderCard(makeSpeechResult({ is_translated: true }))
    expect(screen.getByText('Translated from Hindi')).toBeInTheDocument()
  })

  it('omits "Translated from Hindi" when is_translated is false', () => {
    renderCard(makeSpeechResult({ is_translated: false }))
    expect(screen.queryByText('Translated from Hindi')).toBeNull()
  })

  it('omits View source when source_url is null', () => {
    renderCard(makeSpeechResult({ source_url: null }))
    expect(screen.queryByText('View source ↗')).toBeNull()
  })

  it('displays speaker_name_unresolved records without an error indicator', () => {
    renderCard(
      makeSpeechResult({
        speaker_name: 'Shri Random Name',
        speaker_name_unresolved: true,
      })
    )
    expect(screen.getByText(/Shri Random Name/)).toBeInTheDocument()
    expect(screen.queryByText(/error/i)).toBeNull()
    expect(screen.queryByText(/unresolved/i)).toBeNull()
  })

  it('renders RAW HTML in snippet as literal text — script/img do not become live elements', () => {
    const hostile =
      '<script>alert(1)</script><img src=x onerror="alert(2)"> The <mark>PM</mark> spoke.'
    const { container } = renderCard(makeSpeechResult({ snippet: hostile }))
    const snippet = container.querySelector('[data-testid="snippet"]')
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(snippet.textContent).toContain('<script>alert(1)</script>')
    expect(snippet.textContent).toContain('<img src=x onerror="alert(2)">')
    expect(snippet.querySelector('mark')).not.toBeNull()
    expect(snippet.querySelector('mark').textContent).toBe('PM')
  })

  it('renders a raw <b> tag as literal text rather than bold markup', () => {
    const { container } = renderCard(makeSpeechResult({ snippet: 'A <b>bold</b> claim.' }))
    const snippet = container.querySelector('[data-testid="snippet"]')
    expect(snippet.querySelector('b')).toBeNull()
    expect(snippet.textContent).toContain('<b>bold</b>')
  })

  it('omits session line when session_name is null (CA records)', () => {
    renderCard(makeSpeechResult({ session_name: null, source: 'CA' }))
    expect(screen.getByText('Constituent Assembly')).toBeInTheDocument()
    expect(screen.queryByText('Budget Session 2023')).toBeNull()
  })
})

describe('SpeechCard — F05 v2.0: lang_original badge', () => {
  it('renders "Hindi original" badge for lang_original=hi', () => {
    renderCard(makeSpeechResult({ lang_original: 'hi' }))
    expect(screen.getByTestId('lang-badge')).toHaveTextContent('Hindi original')
  })

  it('renders "Mixed language" badge for lang_original=mixed', () => {
    renderCard(makeSpeechResult({ lang_original: 'mixed' }))
    expect(screen.getByTestId('lang-badge')).toHaveTextContent('Mixed language')
  })

  it('renders no badge for lang_original=en — element absent from DOM', () => {
    renderCard(makeSpeechResult({ lang_original: 'en' }))
    expect(screen.queryByTestId('lang-badge')).toBeNull()
  })

  it('renders no badge when lang_original is null', () => {
    renderCard(makeSpeechResult({ lang_original: null }))
    expect(screen.queryByTestId('lang-badge')).toBeNull()
  })

  it('hi badge renders no "Mixed language" text on the card', () => {
    renderCard(makeSpeechResult({ lang_original: 'hi' }))
    expect(screen.queryByText('Mixed language')).toBeNull()
  })
})

describe('SpeechCard — F05 v2.0: time_of_day', () => {
  it('renders time_of_day verbatim when present', () => {
    renderCard(makeSpeechResult({ time_of_day: '14:35' }))
    expect(screen.getByTestId('time-of-day')).toHaveTextContent('14:35')
  })

  it('does not reformat the time (no 12h conversion)', () => {
    renderCard(makeSpeechResult({ time_of_day: '14:35' }))
    expect(screen.queryByText(/2:35 PM/i)).toBeNull()
    expect(screen.getByTestId('time-of-day').textContent).toBe('14:35')
  })

  it('renders no time element when time_of_day is null — element absent from DOM', () => {
    renderCard(makeSpeechResult({ time_of_day: null }))
    expect(screen.queryByTestId('time-of-day')).toBeNull()
  })
})
