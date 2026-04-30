import { afterEach, describe, expect, it, vi } from 'vitest'
import { useFullscreenToggle } from './useFullscreenToggle'

function setFullscreenElement(element: Element | null) {
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    value: element,
  })
}

function setExitFullscreen(exitFullscreen: () => Promise<void>) {
  Object.defineProperty(document, 'exitFullscreen', {
    configurable: true,
    value: exitFullscreen,
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  setFullscreenElement(null)
})

describe('useFullscreenToggle', () => {
  it('does nothing without a page element', () => {
    const exitFullscreen = vi.fn().mockResolvedValue(undefined)
    setFullscreenElement(document.createElement('div'))
    setExitFullscreen(exitFullscreen)
    const { toggleFullscreen } = useFullscreenToggle<HTMLDivElement>()

    toggleFullscreen()

    expect(exitFullscreen).not.toHaveBeenCalled()
  })

  it('requests fullscreen when the page is not fullscreen', () => {
    const requestFullscreen = vi.fn().mockResolvedValue(undefined)
    const page = document.createElement('div')
    Object.defineProperty(page, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    })
    setFullscreenElement(null)
    const { pageRef, toggleFullscreen } = useFullscreenToggle<HTMLDivElement>()
    pageRef.value = page

    toggleFullscreen()

    expect(requestFullscreen).toHaveBeenCalledTimes(1)
  })

  it('exits fullscreen when a fullscreen element exists', () => {
    const exitFullscreen = vi.fn().mockResolvedValue(undefined)
    const page = document.createElement('div')
    const fullscreenElement = document.createElement('section')
    Object.defineProperty(page, 'requestFullscreen', {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    })
    setFullscreenElement(fullscreenElement)
    setExitFullscreen(exitFullscreen)
    const { pageRef, toggleFullscreen } = useFullscreenToggle<HTMLDivElement>()
    pageRef.value = page

    toggleFullscreen()

    expect(exitFullscreen).toHaveBeenCalledTimes(1)
  })
})
