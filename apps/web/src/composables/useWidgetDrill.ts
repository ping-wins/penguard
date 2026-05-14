import { computed, ref } from 'vue'

export type WidgetDrillMode = 'glance' | 'drill' | 'detail'

export function useWidgetDrill(initial: WidgetDrillMode = 'glance') {
  const mode = ref<WidgetDrillMode>(initial)

  const isGlance = computed(() => mode.value === 'glance')
  const isDrill = computed(() => mode.value === 'drill')
  const isDetail = computed(() => mode.value === 'detail')

  function setMode(next: WidgetDrillMode) {
    mode.value = next
  }

  function openDrill() {
    mode.value = 'drill'
  }

  function openDetail() {
    mode.value = 'detail'
  }

  function close() {
    mode.value = 'glance'
  }

  function toggleDrill() {
    mode.value = mode.value === 'drill' ? 'glance' : 'drill'
  }

  return {
    mode,
    isGlance,
    isDrill,
    isDetail,
    setMode,
    openDrill,
    openDetail,
    close,
    toggleDrill,
  }
}
