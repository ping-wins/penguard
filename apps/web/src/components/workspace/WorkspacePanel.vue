<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  Download,
  Upload,
  Share2,
  Library,
  Presentation,
  X,
  Trash2,
  Plus,
  FileJson,
  AlertCircle,
  CheckCircle2,
  Layers,
  Globe,
  User,
  Clock,
  Tag as TagIcon,
  RefreshCcw,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../../stores/useAuthStore'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { useThemeStore } from '../../stores/useThemeStore'
import {
  deleteCommunityTemplate,
  downloadManifest,
  exportWorkspace,
  importWorkspace,
  installCommunityTemplate,
  listWorkspaceTemplates,
  publishWorkspaceTemplate,
  readManifestFile,
  updatePresentation,
  type CommunityTemplate,
  type PresentationMetadata,
  type PresentationSlide,
  type TemplateCategory,
  type WorkspaceManifest,
  type WorkspaceOrigin,
  type WorkspaceSummary,
} from '../../services/workspaceClient'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const dashboardStore = useDashboardStore()
const themeStore = useThemeStore()

type DialogKind = null | 'export' | 'import' | 'publish' | 'community' | 'presentation' | 'origin'
const openDialog = ref<DialogKind>(null)
const dialogPayload = ref<any>(null)
const errorMsg = ref('')
const successMsg = ref('')
const isBusy = ref(false)

const lastExportedManifest = ref<WorkspaceManifest | null>(null)
const importFile = ref<File | null>(null)
const importPreview = ref<WorkspaceManifest | null>(null)
const publishForm = ref({
  slug: '',
  title: '',
  description: '',
  tagsText: '',
  incidentId: '',
})
const community = ref<CommunityTemplate[]>([])
const communityFilter = ref('')
const communityCategory = ref<TemplateCategory | 'all'>('all')

const CATEGORY_TABS: { value: TemplateCategory | 'all', labelKey: string }[] = [
  { value: 'all', labelKey: 'workspaces.communityDialog.category.all' },
  { value: 'executive', labelKey: 'workspaces.communityDialog.category.executive' },
  { value: 'analyst', labelKey: 'workspaces.communityDialog.category.analyst' },
  { value: 'engineer', labelKey: 'workspaces.communityDialog.category.engineer' },
  { value: 'incident_response', labelKey: 'workspaces.communityDialog.category.incident_response' },
  { value: 'community', labelKey: 'workspaces.communityDialog.category.community' },
]
const presentationDraft = ref<PresentationMetadata>({
  title: '',
  incidentSummary: '',
  presenterName: '',
  audience: 'Executivo',
  severity: 'high',
  slides: [],
})

const workspaces = computed(() => dashboardStore.workspaces)
const activeWorkspaceId = computed(() => dashboardStore.activeWorkspaceId)
const widgets = computed(() => dashboardStore.activeWidgets)
const currentOrigin = computed(() => dashboardStore.activeWorkspaceOrigin)

function resetMessages() {
  errorMsg.value = ''
  successMsg.value = ''
}

function openDialogKind(kind: DialogKind, payload: any = null) {
  resetMessages()
  dialogPayload.value = payload
  if (kind === 'community') loadCommunity()
  if (kind === 'presentation') hydratePresentationDraft()
  openDialog.value = kind
}

function closeDialog() {
  openDialog.value = null
  dialogPayload.value = null
  importFile.value = null
  importPreview.value = null
}

// ----- Export -----
async function handleExport() {
  resetMessages()
  isBusy.value = true
  try {
    const manifest = await exportWorkspace(activeWorkspaceId.value)
    lastExportedManifest.value = manifest
    downloadManifest(manifest)
    successMsg.value = t('workspaces.exportDialog.success', { count: manifest.widgets.length })
  } catch (e: any) {
    errorMsg.value = e?.message ?? t('workspaces.exportDialog.error')
  } finally {
    isBusy.value = false
  }
}

// ----- Import -----
async function handleImportFileChange(event: Event) {
  resetMessages()
  importPreview.value = null
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  importFile.value = file
  try {
    importPreview.value = await readManifestFile(file)
  } catch (e: any) {
    errorMsg.value = e?.message ?? t('workspaces.importDialog.invalidFile')
  }
}

async function handleImportConfirm() {
  if (!importPreview.value) return
  resetMessages()
  isBusy.value = true
  try {
    const result = await importWorkspace(importPreview.value)
    successMsg.value = t('workspaces.importDialog.success', { id: result.id })
    await dashboardStore.switchWorkspace(result.id)
    closeDialog()
  } catch (e: any) {
    errorMsg.value = e?.message ?? t('workspaces.importDialog.error')
  } finally {
    isBusy.value = false
  }
}

// ----- Publish -----
async function handlePublish() {
  resetMessages()
  if (!publishForm.value.slug || !publishForm.value.title) {
    errorMsg.value = t('workspaces.publishDialog.required')
    return
  }
  isBusy.value = true
  try {
    const tags = publishForm.value.tagsText
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)
    await publishWorkspaceTemplate({
      workspaceId: activeWorkspaceId.value,
      slug: publishForm.value.slug,
      title: publishForm.value.title,
      description: publishForm.value.description || undefined,
      tags,
      incidentId: publishForm.value.incidentId || undefined,
    })
    successMsg.value = t('workspaces.publishDialog.success', { title: publishForm.value.title })
    publishForm.value = { slug: '', title: '', description: '', tagsText: '', incidentId: '' }
  } catch (e: any) {
    errorMsg.value = e?.message ?? t('workspaces.publishDialog.error')
  } finally {
    isBusy.value = false
  }
}

// ----- Community -----
async function loadCommunity() {
  isBusy.value = true
  try {
    community.value = await listWorkspaceTemplates({
      category: communityCategory.value,
    })
  } catch (e: any) {
    errorMsg.value = e?.message ?? t('workspaces.communityDialog.loadError')
  } finally {
    isBusy.value = false
  }
}

function selectCategory(category: TemplateCategory | 'all') {
  communityCategory.value = category
  loadCommunity()
}

async function installTemplate(template: CommunityTemplate) {
  resetMessages()
  isBusy.value = true
  try {
    const result = await installCommunityTemplate(template.id)
    successMsg.value = t('workspaces.communityDialog.installSuccess', { title: template.title })
    await dashboardStore.switchWorkspace(result.workspace.id)
    closeDialog()
  } catch (e: any) {
    errorMsg.value = e?.message ?? t('workspaces.communityDialog.installError')
  } finally {
    isBusy.value = false
  }
}

async function removeTemplate(template: CommunityTemplate) {
  resetMessages()
  if (!confirm(t('workspaces.communityDialog.removeConfirm', { title: template.title }))) return
  isBusy.value = true
  try {
    await deleteCommunityTemplate(template.id)
    community.value = community.value.filter((t) => t.id !== template.id)
    successMsg.value = t('workspaces.communityDialog.removed')
  } catch (e: any) {
    errorMsg.value = e?.message ?? t('workspaces.communityDialog.removeError')
  } finally {
    isBusy.value = false
  }
}

const filteredCommunity = computed(() => {
  const q = communityFilter.value.toLowerCase().trim()
  if (!q) return community.value
  return community.value.filter(
    (t) =>
      t.title.toLowerCase().includes(q) ||
      t.slug.includes(q) ||
      (t.tags || []).some((tag) => tag.toLowerCase().includes(q)),
  )
})

// ----- Presentation -----
function hydratePresentationDraft() {
  const widgetList = widgets.value
  presentationDraft.value = {
    title: dashboardStore.workspaceName + t('workspaces.presentationDialog.defaultTitleSuffix'),
    incidentSummary: '',
    presenterName: authStore.user?.displayName ?? '',
    audience: t('workspaces.presentationDialog.defaultAudience'),
    severity: 'high',
    slides: widgetList.map((w: any) => ({
      widgetInstanceId: w.instanceId,
      title: w.catalogId,
      narration: '',
      highlightFieldIds: [],
    })),
  }
}

function addSlide(widgetInstanceId: string) {
  if (presentationDraft.value.slides.some((s) => s.widgetInstanceId === widgetInstanceId)) return
  const widget = widgets.value.find((w: any) => w.instanceId === widgetInstanceId)
  presentationDraft.value.slides.push({
    widgetInstanceId,
    title: widget?.catalogId ?? t('workspaces.presentationDialog.defaultSlideTitle'),
    narration: '',
    highlightFieldIds: [],
  })
}

function removeSlide(slide: PresentationSlide) {
  presentationDraft.value.slides = presentationDraft.value.slides.filter(
    (s) => s.widgetInstanceId !== slide.widgetInstanceId,
  )
}

function moveSlide(index: number, direction: -1 | 1) {
  const slides = presentationDraft.value.slides
  const target = index + direction
  if (target < 0 || target >= slides.length) return
  const [slide] = slides.splice(index, 1)
  slides.splice(target, 0, slide)
}

async function savePresentation() {
  resetMessages()
  isBusy.value = true
  try {
    await updatePresentation(activeWorkspaceId.value, presentationDraft.value)
    successMsg.value = t('workspaces.presentationDialog.saveSuccess')
  } catch (e: any) {
    errorMsg.value = e?.message ?? t('workspaces.presentationDialog.saveError')
  } finally {
    isBusy.value = false
  }
}

async function startPresentation() {
  await savePresentation()
  if (errorMsg.value) return
  router.push({ name: 'presentation', params: { workspaceId: activeWorkspaceId.value } })
}

// ----- Workspaces list -----
async function handleSwitch(workspaceId: string) {
  resetMessages()
  await dashboardStore.switchWorkspace(workspaceId)
}

async function handleDelete(ws: WorkspaceSummary) {
  resetMessages()
  if (ws.id === 'ws_default') {
    errorMsg.value = t('workspaces.cannotDeleteDefault')
    return
  }
  if (!confirm(t('workspaces.deleteConfirm', { name: ws.name }))) return
  try {
    await dashboardStore.deleteWorkspaceById(ws.id)
    successMsg.value = t('workspaces.deletedSuccess')
  } catch (e: any) {
    errorMsg.value = e?.message ?? t('workspaces.deleteError')
  }
}

function originBadge(origin: WorkspaceOrigin | null | undefined) {
  if (!origin || origin.type === 'local') {
    return {
      label: t('workspaces.origins.local'),
      color: 'border-theme-border bg-theme-bg/40 text-theme-text-muted',
    }
  }
  if (origin.type === 'template') {
    return {
      label: t('workspaces.origins.template'),
      color: 'border-purple-500/40 bg-purple-500/15 text-purple-300',
    }
  }
  return {
    label: t('workspaces.origins.imported'),
    color: 'border-sky-500/40 bg-sky-500/15 text-sky-300',
  }
}

function originAuthor(origin: WorkspaceOrigin | null | undefined): string | null {
  if (!origin) return null
  if (origin.type === 'template') return origin.publishedByEmail || null
  if (origin.type === 'imported') return origin.exportedByEmail || null
  return null
}

watch(
  () => openDialog.value,
  (kind) => {
    if (kind !== 'community') return
    loadCommunity()
  },
)

onMounted(() => {
  dashboardStore.refreshWorkspaceList()
  listWorkspaceTemplates({ category: 'all' })
    .then((items) => {
      community.value = items
    })
    .catch(() => undefined)
})

const actions = computed(() => [
  {
    kind: 'export',
    label: t('workspaces.actions.export'),
    icon: Download,
    hint: t('workspaces.actionsHint.export'),
  },
  {
    kind: 'import',
    label: t('workspaces.actions.import'),
    icon: Upload,
    hint: t('workspaces.actionsHint.import'),
  },
  {
    kind: 'presentation',
    label: t('workspaces.actions.presentation'),
    icon: Presentation,
    hint: t('workspaces.actionsHint.presentation'),
  },
  {
    kind: 'publish',
    label: t('workspaces.actions.publish'),
    icon: Share2,
    hint: t('workspaces.actionsHint.publish'),
  },
  {
    kind: 'community',
    label: t('workspaces.actions.library'),
    icon: Library,
    hint: t('workspaces.actionsHint.library', { count: community.value.length }),
  },
])
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- Header -->
    <div class="px-4 pt-4 pb-3 border-b border-theme-border">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="font-bold text-lg text-theme-text flex items-center gap-2">
            <Layers :size="18" />
            {{ t('workspaces.title') }}
          </h2>
          <p class="text-xs text-theme-text-muted mt-1">
            {{ t('workspaces.subtitle') }}
          </p>
        </div>
        <button
          type="button"
          @click="dashboardStore.refreshWorkspaceList()"
          class="text-theme-text-muted hover:text-theme-text"
          :title="t('workspaces.refreshTooltip')"
        >
          <RefreshCcw :size="16" />
        </button>
      </div>
    </div>

    <!-- Actions -->
    <div class="px-4 py-3 border-b border-theme-border grid grid-cols-2 gap-2">
      <button
        v-for="action in actions"
        :key="action.kind"
        type="button"
        :title="action.hint"
        @click="openDialogKind(action.kind as DialogKind)"
        class="flex items-center gap-2 px-3 py-2 rounded-lg border border-theme-border bg-theme-bg/40 text-theme-text text-sm hover:brightness-125 hover:bg-theme-bg/70 transition"
      >
        <component :is="action.icon" :size="14" class="text-theme-text-muted" />
        <span class="truncate">{{ action.label }}</span>
      </button>
    </div>

    <!-- Current origin pill -->
    <div
      v-if="currentOrigin && currentOrigin.type !== 'local'"
      class="px-4 py-3 border-b border-theme-border bg-theme-bg/30"
    >
      <div class="flex items-center justify-between mb-2">
        <span
          class="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border"
          :class="originBadge(currentOrigin).color"
        >
          <Globe v-if="currentOrigin.type === 'template'" :size="11" />
          <Upload v-else :size="11" />
          {{ originBadge(currentOrigin).label }}
        </span>
        <button type="button" @click="openDialogKind('origin', currentOrigin)" class="text-xs text-theme-text-muted hover:text-theme-text underline">
          {{ t('common.details') }}
        </button>
      </div>
      <p v-if="currentOrigin.templateTitle || currentOrigin.description" class="text-sm text-theme-text leading-snug">
        {{ currentOrigin.templateTitle || currentOrigin.description }}
      </p>
      <p v-if="originAuthor(currentOrigin)" class="mt-1 text-xs text-theme-text-muted">
        {{ t('workspaces.origins.authorPrefix', { author: originAuthor(currentOrigin) }) }}
      </p>
      <div
        v-if="currentOrigin.missingProviderTypes && currentOrigin.missingProviderTypes.length"
        class="mt-3 p-2 rounded border border-amber-500/40 bg-amber-500/10 text-xs text-amber-300 flex items-start gap-2"
      >
        <AlertCircle :size="14" class="mt-0.5 shrink-0" />
        <div>
          <div class="font-semibold mb-0.5">{{ t('workspaces.origins.missingProvidersTitle') }}</div>
          <div>{{ t('workspaces.origins.missingProviders', { providers: currentOrigin.missingProviderTypes.join(', ') }) }}</div>
        </div>
      </div>
    </div>

    <!-- List -->
    <div class="flex-1 overflow-y-auto px-4 py-3">
      <h3 class="text-xs font-semibold uppercase tracking-wider text-theme-text-muted mb-2">
        {{ t('workspaces.yourWorkspaces', { count: workspaces.length }) }}
      </h3>
      <ul v-if="workspaces.length" class="space-y-2">
        <li
          v-for="ws in workspaces"
          :key="ws.id"
          class="rounded-lg border p-3 transition-colors"
          :class="ws.id === activeWorkspaceId ? 'border-theme-primary bg-theme-primary/5' : 'border-theme-border bg-theme-bg/40 hover:bg-theme-bg/70'"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1 cursor-pointer" @click="handleSwitch(ws.id)">
              <div class="flex items-center gap-2 mb-1">
                <span class="font-semibold text-theme-text truncate">{{ ws.name }}</span>
                <span
                  v-if="ws.id === activeWorkspaceId"
                  class="text-[10px] uppercase px-1.5 py-0.5 rounded border border-theme-primary/40 bg-theme-primary/10 text-theme-primary font-semibold"
                >
                  {{ t('workspaces.activeBadge') }}
                </span>
              </div>
              <div class="flex items-center gap-2 text-xs text-theme-text-muted flex-wrap">
                <span
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px]"
                  :class="originBadge(ws.origin).color"
                >
                  {{ originBadge(ws.origin).label }}
                </span>
                <span>{{ t('workspaces.widgetsLabel', { count: ws.widgetCount }) }}</span>
                <span v-if="ws.hasPresentation" class="inline-flex items-center gap-1 text-amber-300">
                  <Presentation :size="11" />
                  {{ t('workspaces.presentationBadge') }}
                </span>
              </div>
              <div v-if="originAuthor(ws.origin)" class="text-xs text-theme-text-muted mt-1 truncate">
                {{ t('workspaces.origins.authorPrefix', { author: originAuthor(ws.origin) }) }}
              </div>
            </div>
            <div class="flex flex-col gap-1 shrink-0">
              <button
                v-if="ws.id !== 'ws_default'"
                type="button"
                @click="handleDelete(ws)"
                class="text-theme-text-muted hover:text-red-400 p-1 rounded hover:bg-red-500/10"
                :title="t('workspaces.deleteTooltip')"
              >
                <Trash2 :size="14" />
              </button>
            </div>
          </div>
        </li>
      </ul>
      <p v-else class="text-sm text-theme-text-muted italic">{{ t('workspaces.loadingList') }}</p>
    </div>

    <!-- ===== Modal ===== -->
    <div
      v-if="openDialog"
      class="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-3xl max-h-[85vh] overflow-auto bg-theme-panel border border-theme-border rounded-2xl shadow-2xl p-6 relative">
        <button
          type="button"
          @click="closeDialog"
          class="absolute top-3 right-3 text-theme-text-muted hover:text-theme-text"
          :aria-label="t('common.close')"
        >
          <X :size="18" />
        </button>

        <div v-if="errorMsg" class="mb-3 p-3 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 text-sm flex items-start gap-2">
          <AlertCircle :size="16" class="mt-0.5 shrink-0" />
          <span>{{ errorMsg }}</span>
        </div>
        <div v-if="successMsg" class="mb-3 p-3 rounded-lg border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 text-sm flex items-start gap-2">
          <CheckCircle2 :size="16" class="mt-0.5 shrink-0" />
          <span>{{ successMsg }}</span>
        </div>

        <!-- ORIGIN DETAILS -->
        <div v-if="openDialog === 'origin' && dialogPayload">
          <h2 class="text-xl font-semibold mb-4 text-theme-text">{{ t('workspaces.originDetails.title') }}</h2>
          <div class="space-y-3 text-sm">
            <div class="flex items-center gap-2 text-theme-text-muted">
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs" :class="originBadge(dialogPayload).color">
                <Globe v-if="dialogPayload.type === 'template'" :size="12" />
                <Upload v-else :size="12" />
                {{ originBadge(dialogPayload).label }}
              </span>
            </div>
            <dl class="grid grid-cols-3 gap-x-3 gap-y-3 text-sm">
              <template v-if="dialogPayload.templateTitle">
                <dt class="col-span-1 text-theme-text-muted">{{ t('workspaces.originDetails.labelTitle') }}</dt>
                <dd class="col-span-2 text-theme-text">{{ dialogPayload.templateTitle }}</dd>
              </template>
              <template v-if="dialogPayload.templateSlug">
                <dt class="col-span-1 text-theme-text-muted">{{ t('workspaces.originDetails.slug') }}</dt>
                <dd class="col-span-2 font-mono text-theme-text">@{{ dialogPayload.templateSlug }}</dd>
              </template>
              <template v-if="dialogPayload.publishedByEmail">
                <dt class="col-span-1 text-theme-text-muted flex items-center gap-1"><User :size="13" /> {{ t('workspaces.originDetails.author') }}</dt>
                <dd class="col-span-2 text-theme-text">{{ dialogPayload.publishedByEmail }}</dd>
              </template>
              <template v-if="dialogPayload.exportedByEmail">
                <dt class="col-span-1 text-theme-text-muted flex items-center gap-1"><User :size="13" /> {{ t('workspaces.originDetails.exportedBy') }}</dt>
                <dd class="col-span-2 text-theme-text">{{ dialogPayload.exportedByEmail }}</dd>
              </template>
              <template v-if="dialogPayload.description || dialogPayload.templateDescription">
                <dt class="col-span-1 text-theme-text-muted">{{ t('workspaces.originDetails.description') }}</dt>
                <dd class="col-span-2 text-theme-text whitespace-pre-line">{{ dialogPayload.description || dialogPayload.templateDescription }}</dd>
              </template>
              <template v-if="dialogPayload.tags && dialogPayload.tags.length">
                <dt class="col-span-1 text-theme-text-muted flex items-center gap-1"><TagIcon :size="13" /> {{ t('workspaces.originDetails.tags') }}</dt>
                <dd class="col-span-2 flex flex-wrap gap-1">
                  <span v-for="tag in dialogPayload.tags" :key="tag" class="text-xs px-2 py-0.5 rounded-full border border-theme-border bg-theme-bg/60 text-theme-text-muted">#{{ tag }}</span>
                </dd>
              </template>
              <template v-if="dialogPayload.incidentId">
                <dt class="col-span-1 text-theme-text-muted">{{ t('workspaces.originDetails.incidentId') }}</dt>
                <dd class="col-span-2 font-mono text-theme-text">{{ dialogPayload.incidentId }}</dd>
              </template>
              <template v-if="dialogPayload.sourceWorkspaceId">
                <dt class="col-span-1 text-theme-text-muted">{{ t('workspaces.originDetails.sourceWorkspace') }}</dt>
                <dd class="col-span-2 font-mono text-theme-text">{{ dialogPayload.sourceWorkspaceId }}</dd>
              </template>
              <template v-if="dialogPayload.installedAt || dialogPayload.importedAt || dialogPayload.exportedAt">
                <dt class="col-span-1 text-theme-text-muted flex items-center gap-1"><Clock :size="13" /> {{ t('workspaces.originDetails.date') }}</dt>
                <dd class="col-span-2 text-theme-text">{{ dialogPayload.installedAt || dialogPayload.importedAt || dialogPayload.exportedAt }}</dd>
              </template>
              <template v-if="dialogPayload.installCount !== undefined">
                <dt class="col-span-1 text-theme-text-muted">{{ t('workspaces.originDetails.installs') }}</dt>
                <dd class="col-span-2 text-theme-text">{{ dialogPayload.installCount }}</dd>
              </template>
            </dl>
          </div>
        </div>

        <!-- EXPORT -->
        <div v-if="openDialog === 'export'">
          <h2 class="text-xl font-semibold mb-2 text-theme-text">{{ t('workspaces.exportDialog.title') }}</h2>
          <p class="text-sm text-theme-text-muted mb-4">
            {{ t('workspaces.exportDialog.description') }}
          </p>
          <button
            type="button"
            :disabled="isBusy"
            @click="handleExport"
            class="px-4 py-2 rounded-lg text-white font-medium hover:brightness-110 disabled:opacity-50"
            :style="{ backgroundColor: themeStore.primary }"
          >
            <span v-if="isBusy">{{ t('workspaces.exportDialog.generating') }}</span>
            <span v-else>{{ t('workspaces.exportDialog.download') }}</span>
          </button>
          <pre v-if="lastExportedManifest" class="mt-4 text-xs bg-theme-bg/60 p-3 rounded-lg max-h-72 overflow-auto border border-theme-border">{{ JSON.stringify(lastExportedManifest, null, 2) }}</pre>
        </div>

        <!-- IMPORT -->
        <div v-if="openDialog === 'import'">
          <h2 class="text-xl font-semibold mb-2 text-theme-text">{{ t('workspaces.importDialog.title') }}</h2>
          <p class="text-sm text-theme-text-muted mb-4">
            {{ t('workspaces.importDialog.description') }}
          </p>
          <label class="flex items-center gap-2 px-4 py-3 rounded-lg border border-dashed border-theme-border cursor-pointer hover:brightness-110 text-theme-text">
            <FileJson :size="16" />
            <span>{{ importFile?.name || t('workspaces.importDialog.selectFile') }}</span>
            <input type="file" accept="application/json" @change="handleImportFileChange" class="hidden" />
          </label>
          <div v-if="importPreview" class="mt-4 text-sm text-theme-text space-y-1">
            <div><b>{{ t('workspaces.importDialog.previewName') }}</b> {{ importPreview.name }}</div>
            <div><b>{{ t('workspaces.importDialog.previewWidgets') }}</b> {{ importPreview.widgets?.length ?? 0 }}</div>
            <div><b>{{ t('workspaces.importDialog.previewProviders') }}</b> {{ importPreview.providerTypes?.join(', ') || '—' }}</div>
            <div v-if="importPreview.metadata?.exportedByEmail"><b>{{ t('workspaces.importDialog.previewExportedBy') }}</b> {{ importPreview.metadata.exportedByEmail }}</div>
            <div v-if="importPreview.presentation"><b>{{ t('workspaces.importDialog.previewPresentation') }}</b> {{ importPreview.presentation.title }}</div>
            <button
              type="button"
              :disabled="isBusy"
              @click="handleImportConfirm"
              class="mt-4 px-4 py-2 rounded-lg text-white font-medium hover:brightness-110 disabled:opacity-50"
              :style="{ backgroundColor: themeStore.primary }"
            >
              {{ t('workspaces.importDialog.confirm') }}
            </button>
          </div>
        </div>

        <!-- PUBLISH -->
        <div v-if="openDialog === 'publish'">
          <h2 class="text-xl font-semibold mb-2 text-theme-text">{{ t('workspaces.publishDialog.title') }}</h2>
          <p class="text-sm text-theme-text-muted mb-4">
            {{ t('workspaces.publishDialog.description') }}
          </p>
          <div class="grid grid-cols-2 gap-3">
            <label class="text-sm text-theme-text col-span-1">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.publishDialog.slug') }}</span>
              <input v-model="publishForm.slug" :placeholder="t('workspaces.publishDialog.slugPlaceholder')" class="w-full bg-theme-bg border border-theme-border rounded p-2" />
            </label>
            <label class="text-sm text-theme-text col-span-1">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.publishDialog.titleField') }}</span>
              <input v-model="publishForm.title" :placeholder="t('workspaces.publishDialog.titlePlaceholder')" class="w-full bg-theme-bg border border-theme-border rounded p-2" />
            </label>
            <label class="text-sm text-theme-text col-span-2">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.publishDialog.descField') }}</span>
              <textarea v-model="publishForm.description" rows="3" class="w-full bg-theme-bg border border-theme-border rounded p-2"></textarea>
            </label>
            <label class="text-sm text-theme-text col-span-1">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.publishDialog.tagsField') }}</span>
              <input v-model="publishForm.tagsText" :placeholder="t('workspaces.publishDialog.tagsPlaceholder')" class="w-full bg-theme-bg border border-theme-border rounded p-2" />
            </label>
            <label class="text-sm text-theme-text col-span-1">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.publishDialog.incidentField') }}</span>
              <input v-model="publishForm.incidentId" :placeholder="t('workspaces.publishDialog.incidentPlaceholder')" class="w-full bg-theme-bg border border-theme-border rounded p-2" />
            </label>
          </div>
          <button
            type="button"
            :disabled="isBusy"
            @click="handlePublish"
            class="mt-4 px-4 py-2 rounded-lg text-white font-medium hover:brightness-110 disabled:opacity-50"
            :style="{ backgroundColor: themeStore.primary }"
          >
            {{ t('workspaces.publishDialog.submit') }}
          </button>
        </div>

        <!-- COMMUNITY -->
        <div v-if="openDialog === 'community'">
          <h2 class="text-xl font-semibold mb-2 text-theme-text">{{ t('workspaces.communityDialog.title') }}</h2>
          <div class="flex flex-wrap gap-1.5 mb-3">
            <button
              v-for="tab in CATEGORY_TABS"
              :key="tab.value"
              type="button"
              :disabled="isBusy"
              @click="selectCategory(tab.value)"
              class="px-2.5 py-1 rounded-full text-xs font-medium border transition-colors disabled:opacity-50"
              :class="communityCategory === tab.value
                ? 'border-theme-primary bg-theme-primary/15 text-theme-primary'
                : 'border-theme-border bg-theme-bg/40 text-theme-text-muted hover:text-theme-text'"
            >
              {{ t(tab.labelKey) }}
            </button>
          </div>
          <input
            v-model="communityFilter"
            :placeholder="t('workspaces.communityDialog.filter')"
            class="w-full bg-theme-bg border border-theme-border rounded p-2 mb-3"
          />
          <p v-if="!filteredCommunity.length" class="text-sm text-theme-text-muted">{{ t('workspaces.communityDialog.empty') }}</p>
          <ul class="grid grid-cols-2 gap-3">
            <li
              v-for="template in filteredCommunity"
              :key="template.id"
              class="border border-theme-border rounded-lg p-3 bg-theme-bg/30 flex flex-col"
            >
              <div class="flex-1">
                <div class="flex items-start gap-2 mb-1 flex-wrap">
                  <span class="font-semibold text-theme-text leading-snug">{{ template.title }}</span>
                  <span
                    v-if="template.isCurated"
                    data-test="curated-badge"
                    class="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 font-semibold shrink-0"
                  >
                    {{ t('workspaces.communityDialog.curatedBadge') }}
                  </span>
                </div>
                <div class="text-xs text-theme-text-muted mb-1.5">@{{ template.slug }}</div>
                <p class="text-sm text-theme-text-muted leading-snug">{{ template.description || t('workspaces.communityDialog.noDescription') }}</p>
                <div class="flex items-center gap-1.5 mt-2 flex-wrap">
                  <span
                    v-for="tag in template.tags"
                    :key="tag"
                    class="text-xs px-2 py-0.5 rounded-full border border-theme-border bg-theme-bg/60 text-theme-text-muted"
                  >
                    #{{ tag }}
                  </span>
                </div>
                <div class="text-xs text-theme-text-muted mt-2">
                  {{ t('workspaces.communityDialog.author', { author: template.publishedByEmail || t('workspaces.communityDialog.anonymous') }) }} · {{ t('workspaces.communityDialog.installs', { count: template.installCount }) }}
                </div>
              </div>
              <div class="flex gap-2 mt-3 pt-3 border-t border-theme-border/50">
                <button
                  type="button"
                  :disabled="isBusy"
                  @click="installTemplate(template)"
                  class="flex-1 px-3 py-1.5 rounded-lg text-white text-sm hover:brightness-110 disabled:opacity-50"
                  :style="{ backgroundColor: themeStore.primary }"
                >
                  {{ t('workspaces.communityDialog.install') }}
                </button>
                <button
                  v-if="!template.isCurated && authStore.user?.id === template.publishedByUserId"
                  type="button"
                  :disabled="isBusy"
                  @click="removeTemplate(template)"
                  class="px-2 py-1.5 rounded-lg border border-red-500/40 text-red-300 text-sm hover:bg-red-500/10 disabled:opacity-50 flex items-center gap-1"
                >
                  <Trash2 :size="14" />
                </button>
              </div>
            </li>
          </ul>
        </div>

        <!-- PRESENTATION EDITOR -->
        <div v-if="openDialog === 'presentation'">
          <h2 class="text-xl font-semibold mb-2 text-theme-text">{{ t('workspaces.presentationDialog.title') }}</h2>
          <p class="text-sm text-theme-text-muted mb-4">
            {{ t('workspaces.presentationDialog.description') }}
          </p>
          <div class="grid grid-cols-2 gap-3">
            <label class="text-sm text-theme-text col-span-1">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.presentationDialog.titleField') }}</span>
              <input v-model="presentationDraft.title" class="w-full bg-theme-bg border border-theme-border rounded p-2" />
            </label>
            <label class="text-sm text-theme-text col-span-1">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.presentationDialog.presenter') }}</span>
              <input v-model="presentationDraft.presenterName" class="w-full bg-theme-bg border border-theme-border rounded p-2" />
            </label>
            <label class="text-sm text-theme-text col-span-1">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.presentationDialog.audience') }}</span>
              <input v-model="presentationDraft.audience" class="w-full bg-theme-bg border border-theme-border rounded p-2" />
            </label>
            <label class="text-sm text-theme-text col-span-1">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.presentationDialog.severity') }}</span>
              <select v-model="presentationDraft.severity" class="w-full bg-theme-bg border border-theme-border rounded p-2">
                <option value="critical">{{ t('workspaces.presentationDialog.severityCritical') }}</option>
                <option value="high">{{ t('workspaces.presentationDialog.severityHigh') }}</option>
                <option value="medium">{{ t('workspaces.presentationDialog.severityMedium') }}</option>
                <option value="low">{{ t('workspaces.presentationDialog.severityLow') }}</option>
                <option value="informational">{{ t('workspaces.presentationDialog.severityInformational') }}</option>
              </select>
            </label>
            <label class="text-sm text-theme-text col-span-2">
              <span class="block mb-1 text-theme-text-muted">{{ t('workspaces.presentationDialog.summary') }}</span>
              <textarea v-model="presentationDraft.incidentSummary" rows="3" class="w-full bg-theme-bg border border-theme-border rounded p-2"></textarea>
            </label>
          </div>

          <h3 class="text-md font-semibold mt-5 mb-2 text-theme-text">{{ t('workspaces.presentationDialog.slidesHeader') }}</h3>
          <ul class="space-y-2 mb-3">
            <li
              v-for="(slide, idx) in presentationDraft.slides"
              :key="slide.widgetInstanceId"
              class="flex items-start gap-2 p-2 border border-theme-border rounded bg-theme-bg/30"
            >
              <span class="text-theme-text-muted text-sm pt-2 w-6 text-right">{{ idx + 1 }}.</span>
              <div class="flex-1 grid grid-cols-1 gap-2">
                <input
                  v-model="slide.title"
                  :placeholder="t('workspaces.presentationDialog.slideTitle')"
                  class="w-full bg-theme-bg border border-theme-border rounded p-2 text-sm"
                />
                <textarea
                  v-model="slide.narration"
                  rows="2"
                  :placeholder="t('workspaces.presentationDialog.slideNarration')"
                  class="w-full bg-theme-bg border border-theme-border rounded p-2 text-sm"
                ></textarea>
                <div class="text-xs text-theme-text-muted">{{ t('workspaces.presentationDialog.widgetLabel') }} {{ slide.widgetInstanceId }}</div>
              </div>
              <div class="flex flex-col gap-1">
                <button type="button" @click="moveSlide(idx, -1)" class="text-theme-text-muted hover:text-theme-text text-sm">↑</button>
                <button type="button" @click="moveSlide(idx, 1)" class="text-theme-text-muted hover:text-theme-text text-sm">↓</button>
                <button type="button" @click="removeSlide(slide)" class="text-red-400 hover:text-red-300"><Trash2 :size="14" /></button>
              </div>
            </li>
          </ul>

          <div v-if="widgets.length > presentationDraft.slides.length" class="mb-3">
            <p class="text-xs text-theme-text-muted mb-1">{{ t('workspaces.presentationDialog.addWidgetsHint') }}</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="w in widgets.filter((widget: any) => !presentationDraft.slides.some((s: any) => s.widgetInstanceId === widget.instanceId))"
                :key="w.instanceId"
                type="button"
                @click="addSlide(w.instanceId)"
                class="text-xs px-2 py-1 rounded border border-theme-border text-theme-text hover:brightness-110 flex items-center gap-1"
              >
                <Plus :size="12" />
                {{ w.catalogId }}
              </button>
            </div>
          </div>

          <div class="flex gap-2 mt-4">
            <button
              type="button"
              :disabled="isBusy"
              @click="savePresentation"
              class="px-4 py-2 rounded-lg border border-theme-border text-theme-text hover:brightness-110 disabled:opacity-50"
            >
              {{ t('workspaces.presentationDialog.saveBtn') }}
            </button>
            <button
              type="button"
              :disabled="isBusy || !presentationDraft.slides.length"
              @click="startPresentation"
              class="px-4 py-2 rounded-lg text-white font-medium hover:brightness-110 disabled:opacity-50 flex items-center gap-2"
              :style="{ backgroundColor: themeStore.primary }"
            >
              <Presentation :size="16" />
              {{ t('workspaces.presentationDialog.startBtn') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
