import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const canvas = readFileSync(resolve(root, 'src/components/canvas/DashboardCanvas.vue'), 'utf8')
const store = readFileSync(resolve(root, 'src/stores/useDashboardStore.ts'), 'utf8')

const requiredCanvasSnippets = [
  'v-for="widget in activeWidgets"',
  '<DraggableWidget',
  'v-slot="{ widgetData }"',
  '<component',
  ':is="widgetMap[widget.catalogId]"',
  ':data="widgetData"'
]

const requiredStoreSnippets = [
  'activeWidgets',
  'loadWorkspace',
  'fetchCatalog',
  'addWidget',
  'saveWorkspace'
]

for (const snippet of requiredCanvasSnippets) {
  if (!canvas.includes(snippet)) {
    throw new Error(`DashboardCanvas render contract missing: ${snippet}`)
  }
}

for (const snippet of requiredStoreSnippets) {
  if (!store.includes(snippet)) {
    throw new Error(`Dashboard store contract missing: ${snippet}`)
  }
}

console.log('Canvas render smoke passed')
