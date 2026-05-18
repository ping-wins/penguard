import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  approvePlaybookRun,
  createPlaybookWebhookDestination,
  deletePlaybook,
  createPlaybook,
  listPlaybookRuns,
  listPlaybookNodeTypes,
  listPlaybookWebhookDestinations,
  listPlaybooks,
  runPlaybook,
  simulatePlaybook,
  testPlaybookWebhookDestination,
  updatePlaybook,
  type Playbook,
  type PlaybookDraft,
  type PlaybookNodeType,
  type PlaybookRun,
  type PlaybookSimulation,
  type PlaybookWebhookDestination,
  type PlaybookWebhookDestinationDraft,
  type PlaybookWebhookDestinationTestResult,
} from '../services/playbooksClient'

export const usePlaybooksStore = defineStore('playbooks', () => {
  const playbooks = ref<Playbook[]>([])
  const runHistory = ref<PlaybookRun[]>([])
  const nodeTypes = ref<PlaybookNodeType[]>([])
  const webhookDestinations = ref<PlaybookWebhookDestination[]>([])
  const simulations = ref<Record<string, PlaybookSimulation>>({})
  const runs = ref<Record<string, PlaybookRun>>({})
  const latestRunByPlaybook = ref<Record<string, string>>({})
  const isLoading = ref(false)
  const isSimulating = ref<Record<string, boolean>>({})
  const isRunning = ref<Record<string, boolean>>({})
  const isApproving = ref<Record<string, boolean>>({})
  const isDeleting = ref<Record<string, boolean>>({})
  const isCreating = ref(false)
  const error = ref<string | null>(null)

  const isEmpty = computed(() => !isLoading.value && playbooks.value.length === 0)
  const nodeTypeById = computed(() => Object.fromEntries(nodeTypes.value.map((nodeType) => [nodeType.id, nodeType])))
  const safeActionNodeTypes = computed(() => nodeTypes.value.filter((nodeType) => nodeType.category === 'action' || nodeType.category === 'enrichment' || nodeType.category === 'control'))

  async function refresh() {
    isLoading.value = true
    error.value = null
    try {
      const [nextPlaybooks, nextNodeTypes, nextRunHistory] = await Promise.all([
        listPlaybooks(),
        listPlaybookNodeTypes(),
        listPlaybookRuns(),
      ])
      playbooks.value = nextPlaybooks
      nodeTypes.value = nextNodeTypes
      runHistory.value = nextRunHistory
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to load playbooks'
    } finally {
      isLoading.value = false
    }
  }

  async function loadWebhookDestinations() {
    try {
      webhookDestinations.value = await listPlaybookWebhookDestinations()
    } catch {
      webhookDestinations.value = []
    }
  }

  async function createWebhookDestination(payload: PlaybookWebhookDestinationDraft) {
    error.value = null
    try {
      const result = await createPlaybookWebhookDestination(payload)
      webhookDestinations.value = [
        ...webhookDestinations.value.filter((destination) => destination.id !== result.id),
        result,
      ]
      return result
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to create webhook destination'
      throw e
    }
  }

  async function testWebhookDestination(
    destinationId: string,
    content: string,
  ): Promise<PlaybookWebhookDestinationTestResult> {
    error.value = null
    try {
      return await testPlaybookWebhookDestination(destinationId, content)
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to test webhook destination'
      throw e
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
      runHistory.value = [result, ...runHistory.value.filter((run) => run.id !== result.id)]
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
      runHistory.value = runHistory.value.map((run) => run.id === result.id ? result : run)
      if (!runHistory.value.some((run) => run.id === result.id)) runHistory.value = [result, ...runHistory.value]
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

  async function update(playbookId: string, payload: PlaybookDraft) {
    isCreating.value = true
    error.value = null
    try {
      const result = await updatePlaybook(playbookId, payload)
      playbooks.value = playbooks.value.map((playbook) => playbook.id === result.id ? result : playbook)
      if (!playbooks.value.some((playbook) => playbook.id === result.id)) {
        playbooks.value = [...playbooks.value, result]
      }
      return result
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to update playbook'
      throw e
    } finally {
      isCreating.value = false
    }
  }

  async function remove(playbookId: string) {
    isDeleting.value[playbookId] = true
    error.value = null
    try {
      const result = await deletePlaybook(playbookId)
      playbooks.value = playbooks.value.filter((playbook) => playbook.id !== playbookId)
      delete simulations.value[playbookId]
      return result
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to delete playbook'
      throw e
    } finally {
      isDeleting.value[playbookId] = false
    }
  }

  return {
    playbooks,
    runHistory,
    nodeTypes,
    webhookDestinations,
    simulations,
    runs,
    latestRunByPlaybook,
    isLoading,
    isSimulating,
    isRunning,
    isApproving,
    isDeleting,
    isCreating,
    error,
    isEmpty,
    nodeTypeById,
    safeActionNodeTypes,
    refresh,
    loadWebhookDestinations,
    createWebhookDestination,
    testWebhookDestination,
    simulate,
    run,
    approve,
    create,
    update,
    remove,
  }
})
