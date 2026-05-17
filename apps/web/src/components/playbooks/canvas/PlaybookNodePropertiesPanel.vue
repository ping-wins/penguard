<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PlaybookFlowNode } from '../../../utils/playbookGraph'

const props = defineProps<{
  node: PlaybookFlowNode | null
}>()
const emit = defineEmits<{
  updateConfig: [nodeId: string, config: Record<string, unknown>]
}>()

const { t } = useI18n()
const configText = ref('{}')
const error = ref('')
const title = computed(() => props.node?.data.label ?? t('playbooks.canvas.noNodeSelected'))

watch(
  () => props.node?.id,
  () => {
    configText.value = JSON.stringify(props.node?.data.config ?? {}, null, 2)
    error.value = ''
  },
  { immediate: true },
)

function applyConfig() {
  if (!props.node) return
  try {
    const parsed = JSON.parse(configText.value || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(t('playbooks.canvas.configObjectRequired'))
    }
    emit('updateConfig', props.node.id, parsed)
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('playbooks.canvas.invalidConfig')
  }
}
</script>

<template>
  <aside class="flex min-h-0 flex-col gap-2 rounded border border-theme-border bg-theme-bg/80 p-3">
    <div>
      <div class="text-xs font-semibold text-theme-text">{{ title }}</div>
      <div v-if="props.node" class="mt-0.5 font-mono text-[10px] text-theme-text-muted">
        {{ props.node.data.nodeType }}
      </div>
    </div>
    <template v-if="props.node">
      <label class="grid gap-1">
        <span class="text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
          {{ t('playbooks.canvas.nodeConfig') }}
        </span>
        <textarea
          v-model="configText"
          data-test="playbook-node-config"
          class="min-h-[120px] resize-none rounded border border-theme-border bg-theme-panel p-2 font-mono text-[11px] text-theme-text outline-none focus:border-theme-primary"
          spellcheck="false"
        />
      </label>
      <div v-if="error" class="text-xs text-red-300">{{ error }}</div>
      <button
        type="button"
        data-test="playbook-node-config-apply"
        class="rounded border border-theme-primary/40 bg-theme-primary/10 px-2 py-1 text-xs font-semibold text-theme-primary hover:bg-theme-primary/20"
        @click="applyConfig"
      >
        {{ t('playbooks.canvas.applyConfig') }}
      </button>
    </template>
    <div v-else class="text-xs text-theme-text-muted">
      {{ t('playbooks.canvas.selectNode') }}
    </div>
  </aside>
</template>
