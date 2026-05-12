import { onBeforeUnmount, ref } from 'vue'

// Mounts a pointer-driven resize handle on the edge of a panel.
// `edge` says which side the handle lives on, so the delta sign matches the
// user's intuition: dragging the build pane's left edge to the right shrinks
// the panel; dragging the sidebar drawer's right edge to the right grows it.

export type DragEdge = 'left' | 'right'

export type UseDraggableEdgeOptions = {
  edge: DragEdge
  getCurrent: () => number
  setValue: (next: number) => void
  min: number
  max: number
}

export function useDraggableEdge(options: UseDraggableEdgeOptions) {
  const isDragging = ref(false)
  let startX = 0
  let startWidth = 0

  function onPointerMove(event: PointerEvent) {
    const delta = event.clientX - startX
    const direction = options.edge === 'right' ? 1 : -1
    const candidate = startWidth + delta * direction
    const clamped = Math.min(Math.max(candidate, options.min), options.max)
    options.setValue(clamped)
  }

  function onPointerUp() {
    if (!isDragging.value) return
    isDragging.value = false
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
  }

  function onPointerDown(event: PointerEvent) {
    if (event.button !== 0) return
    event.preventDefault()
    isDragging.value = true
    startX = event.clientX
    startWidth = options.getCurrent()
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
  }

  onBeforeUnmount(() => {
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', onPointerUp)
  })

  return {
    isDragging,
    onPointerDown,
  }
}
