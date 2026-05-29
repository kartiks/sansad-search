import '@testing-library/jest-dom'

// jsdom doesn't implement window.scrollTo — stub it to keep test output clean.
if (typeof window !== 'undefined') {
  window.scrollTo = () => {}
}
