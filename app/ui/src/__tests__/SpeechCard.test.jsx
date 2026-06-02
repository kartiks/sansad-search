import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SpeechCard from '../components/SpeechCard.jsx'
import { makeSpeechResult } from './fixtures.js'

describe('SpeechCard — base rendering', () => {
  it('renders metadata row with proceeding badge, body, date, session', () => {
    render(<SpeechCard result={makeSpeechResult()} />)
    expect(screen.getByText('Debate')).toBeInTheDocument()
    expect(screen.getByText('Lok Sabha')).toBeInTheDocument()
    expect(screen.getByText('15 March 2023')).toBeInTheDocument()
    expect(screen.getByText('Budget Session 2023')).toBeInTheDocument()
  })

  it('renders the speaker name', () => {
    render(<SpeechCard result={makeSpeechResult()} />)
    expect(screen.getByText(/Jairam Ramesh/)).toBeInTheDocument()
  })

  it('renders the subject line', () => {
    render(<SpeechCard result={makeSpeechResult()} />)
    expect(
      screen.getByText('General Discussion on the Union Budget')
    ).toBeInTheDocument()
  })

  it('renders the snippet with mark highlights', () => {
    render(<SpeechCard result={makeSpeechResult()} />)
    const snippet = screen.getByTestId('snippet')
    expect(snippet.innerHTML).toContain('<mark>PM</mark>')
  })

  it('renders View source link with new-tab attributes', () => {
    render(<SpeechCard result={makeSpeechResult()} />)
    const link = screen.getByText('View source ↗')
    expect(link).toHaveAttribute('href', 'https://sansad.in/example')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })
})

describe('SpeechCard — F05 edge cases', () => {
  it('shows "Speaker unknown" when speaker_name is null', () => {
    render(
      <SpeechCard
        result={makeSpeechResult({ speaker_name: null, speaker_party: null, speaker_constituency_or_state: null })}
      />
    )
    expect(screen.getByText('Speaker unknown')).toBeInTheDocument()
  })

  it('omits party and constituency when both absent (no placeholder)', () => {
    render(
      <SpeechCard
        result={makeSpeechResult({ speaker_party: null, speaker_constituency_or_state: null })}
      />
    )
    expect(screen.queryByText(/INC/)).toBeNull()
    expect(screen.queryByText(/Karnataka/)).toBeNull()
  })

  it('shows party alone when constituency is missing', () => {
    render(
      <SpeechCard
        result={makeSpeechResult({ speaker_constituency_or_state: null })}
      />
    )
    expect(screen.getByText(/INC/)).toBeInTheDocument()
    expect(screen.queryByText(/Karnataka/)).toBeNull()
  })

  it('renders untranslated placeholder when snippet field is missing', () => {
    render(
      <SpeechCard
        result={makeSpeechResult({ snippet: undefined, snippet_from_supplementary: undefined })}
      />
    )
    expect(
      screen.getByText('This speech was delivered in Hindi. No English text is available.')
    ).toBeInTheDocument()
  })

  it('renders untranslated placeholder when snippet is explicitly null', () => {
    render(<SpeechCard result={makeSpeechResult({ snippet: null })} />)
    expect(screen.getByTestId('untranslated-placeholder')).toBeInTheDocument()
  })

  it('still shows all metadata for untranslated speech', () => {
    render(<SpeechCard result={makeSpeechResult({ snippet: null })} />)
    expect(screen.getByText('Debate')).toBeInTheDocument()
    expect(screen.getByText('Lok Sabha')).toBeInTheDocument()
    expect(screen.getByText('15 March 2023')).toBeInTheDocument()
    expect(screen.getByText('Jairam Ramesh')).toBeInTheDocument()
  })

  it('shows "Translated from Hindi" indicator when is_translated is true', () => {
    render(<SpeechCard result={makeSpeechResult({ is_translated: true })} />)
    expect(screen.getByText('Translated from Hindi')).toBeInTheDocument()
  })

  it('omits "Translated from Hindi" when is_translated is false', () => {
    render(<SpeechCard result={makeSpeechResult({ is_translated: false })} />)
    expect(screen.queryByText('Translated from Hindi')).toBeNull()
  })

  it('omits View source when source_url is null', () => {
    render(<SpeechCard result={makeSpeechResult({ source_url: null })} />)
    expect(screen.queryByText('View source ↗')).toBeNull()
  })

  it('displays speaker_name_unresolved records without an error indicator', () => {
    render(
      <SpeechCard
        result={makeSpeechResult({
          speaker_name: 'Shri Random Name',
          speaker_name_unresolved: true,
        })}
      />
    )
    expect(screen.getByText(/Shri Random Name/)).toBeInTheDocument()
    expect(screen.queryByText(/error/i)).toBeNull()
    expect(screen.queryByText(/unresolved/i)).toBeNull()
  })

  it('renders RAW HTML in snippet as literal text — script/img do not become live elements', () => {
    // Feed UNESCAPED hostile markup directly (not pre-escaped entities) to
    // exercise the dangerouslySetInnerHTML path against a real attack payload.
    const hostile =
      '<script>alert(1)</script><img src=x onerror="alert(2)"> The <mark>PM</mark> spoke.'
    const { container } = render(
      <SpeechCard result={makeSpeechResult({ snippet: hostile })} />
    )
    const snippet = container.querySelector('[data-testid="snippet"]')
    // No injected element may become live in the DOM
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    // The raw tags must appear as literal text
    expect(snippet.textContent).toContain('<script>alert(1)</script>')
    expect(snippet.textContent).toContain('<img src=x onerror="alert(2)">')
    // The legitimate <mark> highlight survives as real markup
    expect(snippet.querySelector('mark')).not.toBeNull()
    expect(snippet.querySelector('mark').textContent).toBe('PM')
  })

  it('renders a raw <b> tag as literal text rather than bold markup', () => {
    const { container } = render(
      <SpeechCard result={makeSpeechResult({ snippet: 'A <b>bold</b> claim.' })} />
    )
    const snippet = container.querySelector('[data-testid="snippet"]')
    expect(snippet.querySelector('b')).toBeNull()
    expect(snippet.textContent).toContain('<b>bold</b>')
  })

  it('omits session line when session_name is null (CA records)', () => {
    render(<SpeechCard result={makeSpeechResult({ session_name: null, source: 'CA' })} />)
    expect(screen.getByText('Constituent Assembly')).toBeInTheDocument()
    expect(screen.queryByText('Budget Session 2023')).toBeNull()
  })
})

describe('SpeechCard — F05 v2.0: lang_original badge', () => {
  it('renders "Hindi original" badge for lang_original=hi', () => {
    render(<SpeechCard result={makeSpeechResult({ lang_original: 'hi' })} />)
    expect(screen.getByTestId('lang-badge')).toHaveTextContent('Hindi original')
  })

  it('renders "Mixed language" badge for lang_original=mixed', () => {
    render(<SpeechCard result={makeSpeechResult({ lang_original: 'mixed' })} />)
    expect(screen.getByTestId('lang-badge')).toHaveTextContent('Mixed language')
  })

  it('renders no badge for lang_original=en — element absent from DOM', () => {
    render(<SpeechCard result={makeSpeechResult({ lang_original: 'en' })} />)
    expect(screen.queryByTestId('lang-badge')).toBeNull()
  })

  it('renders no badge when lang_original is null', () => {
    render(<SpeechCard result={makeSpeechResult({ lang_original: null })} />)
    expect(screen.queryByTestId('lang-badge')).toBeNull()
  })

  it('hi badge renders no "Mixed language" text on the card', () => {
    render(<SpeechCard result={makeSpeechResult({ lang_original: 'hi' })} />)
    expect(screen.queryByText('Mixed language')).toBeNull()
  })
})

describe('SpeechCard — F05 v2.0: time_of_day', () => {
  it('renders time_of_day verbatim when present', () => {
    render(<SpeechCard result={makeSpeechResult({ time_of_day: '14:35' })} />)
    expect(screen.getByTestId('time-of-day')).toHaveTextContent('14:35')
  })

  it('does not reformat the time (no 12h conversion)', () => {
    render(<SpeechCard result={makeSpeechResult({ time_of_day: '14:35' })} />)
    expect(screen.queryByText(/2:35 PM/i)).toBeNull()
    expect(screen.getByTestId('time-of-day').textContent).toBe('14:35')
  })

  it('renders no time element when time_of_day is null — element absent from DOM', () => {
    render(<SpeechCard result={makeSpeechResult({ time_of_day: null })} />)
    expect(screen.queryByTestId('time-of-day')).toBeNull()
  })
})
