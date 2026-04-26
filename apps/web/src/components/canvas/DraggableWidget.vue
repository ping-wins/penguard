<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { X, GripHorizontal } from 'lucide-vue-next'

const props = defineProps<{
  instanceId: string
  catalogId: string
  layout: { x: number; y: number; w: number; h: number; z: number }
}>()

const store = useDashboardStore()
const isDragging = ref(false)
const zoom = computed(() => store.zoom)

// Dimensões exatas em pixels
const widthPx = computed(() => props.layout.w)
const heightPx = computed(() => props.layout.h)

function handleRemove() {
  store.removeWidget(props.instanceId)
}

function bringToFront() {
  store.bringToFront(props.instanceId)
}

let startX = 0
let startY = 0
let initialDragX = 0
let initialDragY = 0

function startDrag(e: PointerEvent) {
  isDragging.value = true
  bringToFront()
  
  startX = e.clientX
  startY = e.clientY
  initialDragX = props.layout.x
  initialDragY = props.layout.y
  
  window.addEventListener('pointermove', onDrag)
  window.addEventListener('pointerup', stopDrag)
  e.preventDefault()
}

function onDrag(e: PointerEvent) {
  if (!isDragging.value) return
  const dx = (e.clientX - startX) / zoom.value
  const dy = (e.clientY - startY) / zoom.value
  
  let newX = Math.max(0, initialDragX + dx)
  let newY = Math.max(0, initialDragY + dy)
  
  store.updateWidgetPosition(props.instanceId, newX, newY)
}

function stopDrag() {
  isDragging.value = false
  window.removeEventListener('pointermove', onDrag)
  window.removeEventListener('pointerup', stopDrag)
}

let startResizeX = 0
let startResizeY = 0
let initialW = 0
let initialH = 0
let initialX = 0
let initialY = 0
let resizeDir = ''

function startResize(e: PointerEvent, dir: string) {
  bringToFront()
  startResizeX = e.clientX
  startResizeY = e.clientY
  initialW = props.layout.w
  initialH = props.layout.h
  initialX = props.layout.x
  initialY = props.layout.y
  resizeDir = dir
  
  window.addEventListener('pointermove', onResize)
  window.addEventListener('pointerup', stopResize)
  e.preventDefault()
  e.stopPropagation()
}

function onResize(e: PointerEvent) {
  const dx = (e.clientX - startResizeX) / zoom.value
  const dy = (e.clientY - startResizeY) / zoom.value
  
  let newW = initialW
  let newH = initialH
  let newX = initialX
  let newY = initialY
  
  const minW = 150
  const minH = 100

  if (resizeDir.includes('e')) {
    newW = Math.max(minW, initialW + dx)
  } else if (resizeDir.includes('w')) {
    newW = Math.max(minW, initialW - dx)
    newX = initialX + (initialW - newW)
  }
  
  if (resizeDir.includes('s')) {
    newH = Math.max(minH, initialH + dy)
  } else if (resizeDir.includes('n')) {
    newH = Math.max(minH, initialH - dy)
    newY = initialY + (initialH - newH)
  }
  
  store.updateWidgetSize(props.instanceId, newW, newH)
  if (newX !== initialX || newY !== initialY) {
    store.updateWidgetPosition(props.instanceId, newX, newY)
  }
}

function stopResize() {
  window.removeEventListener('pointermove', onResize)
  window.removeEventListener('pointerup', stopResize)
}
</script>

<template>
  <div
    class="absolute flex flex-col bg-theme-panel border border-theme-border rounded-md shadow-2xl transition-shadow group"
    :class="{ 'ring-2 ring-theme-primary/50 shadow-theme-primary/10': isDragging }"
    :style="{
      width: `${widthPx}px`,
      height: `${heightPx}px`,
      transform: `translate(${layout.x}px, ${layout.y}px)`,
      zIndex: layout.z
    }"
    @mousedown="bringToFront"
    v-motion
    :initial="{ opacity: 0, scale: 0.9, y: 20 }"
    :enter="{ opacity: 1, scale: 1, y: 0, transition: { type: 'spring', stiffness: 250, damping: 20 } }"
  >
    <!-- Header -->
    <div 
      class="h-10 bg-theme-bg/80 border-b border-theme-border flex items-center justify-between px-3 cursor-move select-none rounded-t-md"
      @pointerdown="startDrag"
    >
      <div class="flex items-center gap-2 text-theme-text-muted">
        <GripHorizontal :size="16" />
        <span class="text-xs font-semibold text-theme-text uppercase tracking-wider">{{ catalogId }}</span>
      </div>
      <button @click.stop="handleRemove" class="text-theme-text-muted hover:text-theme-primary transition-colors" title="Remove Widget">
        <X :size="16" />
      </button>
    </div>

    <!-- Content slot -->
    <div class="flex-1 p-4 overflow-hidden relative pointer-events-auto bg-gradient-to-br from-transparent to-black/10 rounded-b-md">
      <slot />
    </div>

    <!-- Handles - Visíveis no hover do container -->
    <div class="opacity-0 group-hover:opacity-100 transition-opacity">
      <!-- Edges -->
      <div class="absolute top-0 left-2 right-2 h-1.5 cursor-ns-resize -translate-y-1/2" @pointerdown.stop="startResize($event, 'n')"></div>
      <div class="absolute bottom-0 left-2 right-2 h-1.5 cursor-ns-resize translate-y-1/2" @pointerdown.stop="startResize($event, 's')"></div>
      <div class="absolute top-2 bottom-2 left-0 w-1.5 cursor-ew-resize -translate-x-1/2" @pointerdown.stop="startResize($event, 'w')"></div>
      <div class="absolute top-2 bottom-2 right-0 w-1.5 cursor-ew-resize translate-x-1/2" @pointerdown.stop="startResize($event, 'e')"></div>
      
      <!-- Corners -->
      <div class="absolute top-0 left-0 w-3 h-3 cursor-nwse-resize -translate-x-1/2 -translate-y-1/2 z-10" @pointerdown.stop="startResize($event, 'nw')"></div>
      <div class="absolute top-0 right-0 w-3 h-3 cursor-nesw-resize translate-x-1/2 -translate-y-1/2 z-10" @pointerdown.stop="startResize($event, 'ne')"></div>
      <div class="absolute bottom-0 left-0 w-3 h-3 cursor-nesw-resize -translate-x-1/2 translate-y-1/2 z-10" @pointerdown.stop="startResize($event, 'sw')"></div>
      
      <div 
        class="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize flex items-end justify-end p-0.5 hover:text-theme-primary transition-colors text-theme-text-muted z-10" 
        @pointerdown.stop="startResize($event, 'se')"
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <path d="M21 15l-6 6M21 9l-12 12M21 3l-18 18" />
        </svg>
      </div>
    </div>
  </div>
</template>
