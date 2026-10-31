import '@testing-library/jest-dom'

// jsdom doesn't implement window.scrollTo — stub it to keep test output clean.
if (typeof window !== 'undefined') {
  window.scrollTo = () => {}
}

// Node 25 ships its own global `localStorage`, which shadows jsdom's and has
// no working methods unless Node is started with --localstorage-file. Install
// a small in-memory Storage so tests behave the same on every Node version.
class MemoryStorage {
  constructor() {
    this._data = new Map()
  }
  get length() {
    return this._data.size
  }
  key(i) {
    return Array.from(this._data.keys())[i] ?? null
  }
  getItem(k) {
    return this._data.has(String(k)) ? this._data.get(String(k)) : null
  }
  setItem(k, v) {
    this._data.set(String(k), String(v))
  }
  removeItem(k) {
    this._data.delete(String(k))
  }
  clear() {
    this._data.clear()
  }
}

if (typeof window !== 'undefined') {
  const storage = new MemoryStorage()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    get: () => storage,
  })
  if (globalThis !== window) {
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get: () => storage,
    })
  }
}
