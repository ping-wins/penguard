import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  approvePlaybookRun,
  createPlaybook,
  listPlaybookNodeTypes,
  listPlaybooks,
  runPlaybook,
  simulatePlaybook,
  type Playbook,
  type PlaybookDraft,
  type PlaybookNodeType,
  type PlaybookRun,
  type PlaybookSimulation,
} from '../services/playbooksClient'

export const usePlaybooksStore = defineStore('playbooks', () => {
  const playbooks = ref<Playbook[]>([])
  const nodeTypes = ref<PlaybookNodeType[]>([])
  const simulations = ref<Record<string, PlaybookSimulation>>({})
  const runs = ref<Record<string, PlaybookRun>>({})
  const latestRunByPlaybook = ref<Record<string, string>>({})
  const isLoading = ref(false)
  const isSimulating = ref<Record<string, boolean>>({})
  const isRunning = ref<Record<string, boolean>>({})
  const isApproving = ref<Record<string, boolean>>({})
  const isCreating = ref(false)
  const error = ref<string | null>(null)

  const isEmpty = computed(() => !isLoading.value && playbooks.value.length === 0)
  const nodeTypeById = computed(() => Object.fromEntries(nodeTypes.value.map((nodeType) => [nodeType.id, nodeType])))
  const safeActionNodeTypes = computed(() => nodeTypes.value.filter((nodeType) => nodeType.category === 'action' || nodeType.category === 'enrichment' || nodeType.category === 'control'))

  async function refresh() {
    isLoading.value = true
    error.value = null
    try {
      const [nextPlaybooks, nextNodeTypes] = await Promise.all([
        listPlaybooks(),
        listPlaybookNodeTypes(),
      ])
      playbooks.value = nextPlaybooks
      nodeTypes.value = nextNodeTypes
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to load playbooks'
    } finally {
      isLoading.value = false
    }
  }

  async function simulate(playbookId: string) {
    isSimulating.value[playbookId] = true
    error.value = null
    try {
      const result = await simulatePlaybook(playbookId)
      simulations.value[playbookId] = result
      return result
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to simulate playbook'
      throw e
    } finally {
      isSimulating.value[playbookId] = false
    }
  }

  async function run(incidentId: string, playbookId: string) {
    isRunning.value[playbookId] = true
    error.value = null
    try {
      const result = await runPlaybook(incidentId, playbookId)
      runs.value[result.id] = result
      latestRunByPlaybook.value[playbookId] = result.id
      return result
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to run playbook'
      throw e
    } finally {
      isRunning.value[playbookId] = false
    }
  }

  async function approve(runId: string) {
    isApproving.value[runId] = true
    error.value = null
    try {
      const result = await approvePlaybookRun(runId)
      runs.value[result.id] = result
      if (result.playbookId) latestRunByPlaybook.value[result.playbookId] = result.id
      return result
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to approve playbook run'
      throw e
    } finally {
      isApproving.value[runId] = false
    }
  }

  async function create(payload: PlaybookDraft) {
    isCreating.value = true
    error.value = null
    try {
      const result = await createPlaybook(payload)
      playbooks.value = [...playbooks.value.filter((playbook) => playbook.id !== result.id), result]
      return result
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to create playbook'
      throw e
    } finally {
      isCreating.value = false
    }
  }

  return {
    playbooks,
    nodeTypes,
    simulations,
    runs,
    latestRunByPlaybook,
    isLoading,
    isSimulating,
    isRunning,
    isApproving,
    isCreating,
    error,
    isEmpty,
    nodeTypeById,
    safeActionNodeTypes,
    refresh,
    simulate,
    run,
    approve,
    create,
  }
})
