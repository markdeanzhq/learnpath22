import { ref } from 'vue'

export function useFullscreenToggle<T extends HTMLElement = HTMLElement>() {
  const pageRef = ref<T>()

  function toggleFullscreen() {
    const page = pageRef.value
    if (!page) return

    if (document.fullscreenElement) {
      void document.exitFullscreen()
      return
    }

    void page.requestFullscreen()
  }

  return {
    pageRef,
    toggleFullscreen,
  }
}
