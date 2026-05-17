<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Plus,
  Trash2,
  Users as UsersIcon,
  ShieldCheck,
  UserPlus,
  X,
  Search,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRolesStore } from '../../stores/useRolesStore'

const { t, te } = useI18n()
const store = useRolesStore()

type Mode = 'roles' | 'users'
type SubTab = 'display' | 'permissions' | 'members'

const mode = ref<Mode>('roles')
const subTab = ref<SubTab>('display')
const userSearch = ref('')
const createOpen = ref(false)
const addMemberOpen = ref(false)
const newRoleName = ref('')
const newRoleColor = ref('#5865F2')
const newMemberInput = ref('')
const editDraft = ref<{ name: string; description: string; color: string } | null>(null)
const editPermsDraft = ref<Set<string>>(new Set())
const saving = ref(false)

onMounted(async () => {
  await store.fetchAll()
})

watch(
  () => store.selectedRole,
  (role) => {
    if (!role) {
      editDraft.value = null
      editPermsDraft.value = new Set()
      return
    }
    editDraft.value = {
      name: role.name,
      description: role.description ?? '',
      color: role.color ?? '#5865F2',
    }
    editPermsDraft.value = new Set(role.permissions)
  },
  { immediate: true },
)

watch(mode, (next) => {
  if (next === 'users' && store.users.length === 0) {
    void store.fetchUsers()
  }
})

const isDirty = computed(() => {
  const role = store.selectedRole
  if (!role || !editDraft.value) return false
  if (role.isSystem) return false
  if (editDraft.value.name !== role.name) return true
  if ((editDraft.value.description ?? '') !== (role.description ?? '')) return true
  if ((editDraft.value.color ?? '') !== (role.color ?? '')) return true
  const a = [...editPermsDraft.value].sort().join(',')
  const b = [...role.permissions].sort().join(',')
  return a !== b
})

function ts(key: string, fallback: string): string {
  return te(key) ? t(key) : fallback
}

async function handleCreateRole() {
  if (!newRoleName.value.trim()) return
  try {
    await store.createRole({
      name: newRoleName.value.trim(),
      color: newRoleColor.value,
      permissions: [],
    })
    createOpen.value = false
    newRoleName.value = ''
    newRoleColor.value = '#5865F2'
  } catch {
    // error surfaces via store.error
  }
}

async function handleSave() {
  const role = store.selectedRole
  if (!role || !editDraft.value) return
  saving.value = true
  try {
    await store.updateRole(role.id, {
      name: editDraft.value.name.trim(),
      description: editDraft.value.description,
      color: editDraft.value.color,
      permissions: role.isSystem ? undefined : [...editPermsDraft.value],
    })
  } finally {
    saving.value = false
  }
}

async function handleDelete(roleId: string, name: string) {
  if (!window.confirm(t('settings.roles.delete.confirm', { name }))) return
  await store.deleteRole(roleId)
}

function togglePerm(slug: string) {
  if (editPermsDraft.value.has(slug)) editPermsDraft.value.delete(slug)
  else editPermsDraft.value.add(slug)
  editPermsDraft.value = new Set(editPermsDraft.value)
}

async function handleAddMember() {
  const role = store.selectedRole
  if (!role || !newMemberInput.value.trim()) return
  const input = newMemberInput.value.trim()
  const body = input.includes('@') ? { email: input } : { userId: input }
  try {
    await store.addMember(role.id, body)
    addMemberOpen.value = false
    newMemberInput.value = ''
  } catch {
    // surfaces via store.error
  }
}

async function handleSearchUsers() {
  await store.fetchUsers(userSearch.value || null)
}

async function toggleUserRole(userId: string, roleId: string, hasIt: boolean) {
  if (hasIt) await store.setUserRoles(userId, [], [roleId])
  else await store.setUserRoles(userId, [roleId], [])
}
</script>

<template>
  <section class="flex h-full min-h-0">
    <!-- Left pane: role/user list -->
    <aside class="flex w-64 shrink-0 flex-col border-r border-theme-border bg-theme-bg/40">
      <div class="flex items-center gap-1 border-b border-theme-border p-2">
        <button
          type="button"
          class="flex-1 rounded px-2 py-1 text-xs font-medium transition-colors"
          :class="mode === 'roles' ? 'bg-theme-primary/15 text-theme-primary' : 'text-theme-text-muted hover:text-theme-text'"
          data-testid="roles-mode-roles"
          @click="mode = 'roles'"
        >
          <ShieldCheck :size="13" class="inline-block mr-1" />
          {{ ts('settings.roles.tabs.roles', 'Cargos') }}
        </button>
        <button
          type="button"
          class="flex-1 rounded px-2 py-1 text-xs font-medium transition-colors"
          :class="mode === 'users' ? 'bg-theme-primary/15 text-theme-primary' : 'text-theme-text-muted hover:text-theme-text'"
          data-testid="roles-mode-users"
          @click="mode = 'users'"
        >
          <UsersIcon :size="13" class="inline-block mr-1" />
          {{ ts('settings.roles.tabs.users', 'Usuários') }}
        </button>
      </div>

      <!-- Roles list -->
      <div v-if="mode === 'roles'" class="flex-1 min-h-0 overflow-y-auto">
        <div class="flex items-center justify-between px-3 py-2">
          <span class="text-[10px] font-semibold uppercase tracking-wider text-theme-text-muted">
            {{ ts('settings.roles.listTitle', 'Cargos') }}
          </span>
          <button
            type="button"
            class="rounded p-1 text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text"
            data-testid="roles-create-open"
            :title="ts('settings.roles.create', 'Criar cargo')"
            @click="createOpen = true"
          >
            <Plus :size="14" />
          </button>
        </div>
        <ul class="flex flex-col gap-0.5 px-1 pb-2">
          <li
            v-for="role in store.roles"
            :key="role.id"
            class="rounded px-2 py-1.5 cursor-pointer transition-colors"
            :class="role.id === store.selectedRoleId ? 'bg-theme-primary/10' : 'hover:bg-theme-border/40'"
            data-testid="roles-list-item"
            @click="store.selectRole(role.id)"
          >
            <div class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 rounded-full" :style="{ backgroundColor: role.color ?? '#888' }" />
              <span class="flex-1 truncate text-sm text-theme-text">{{ role.name }}</span>
              <span class="rounded bg-theme-border/60 px-1.5 py-0.5 text-[10px] text-theme-text-muted">
                {{ role.memberCount }}
              </span>
            </div>
            <div v-if="role.isSystem" class="mt-0.5 text-[10px] uppercase tracking-wider text-theme-text-muted">
              {{ ts('settings.roles.system', 'system') }}
            </div>
          </li>
          <li v-if="!store.isLoading && store.roles.length === 0" class="px-3 py-4 text-xs text-theme-text-muted">
            {{ ts('settings.roles.empty', 'Nenhum cargo criado ainda.') }}
          </li>
        </ul>
      </div>

      <!-- Users list -->
      <div v-else class="flex flex-1 min-h-0 flex-col">
        <form class="flex gap-1 border-b border-theme-border p-2" @submit.prevent="handleSearchUsers">
          <div class="relative flex-1">
            <Search :size="12" class="absolute left-2 top-1/2 -translate-y-1/2 text-theme-text-muted" />
            <input
              v-model="userSearch"
              type="text"
              :placeholder="ts('settings.users.searchPlaceholder', 'Buscar usuário')"
              class="w-full rounded border border-theme-border bg-theme-panel pl-6 pr-2 py-1 text-xs text-theme-text outline-none focus:border-theme-primary"
            />
          </div>
        </form>
        <ul class="flex-1 min-h-0 overflow-y-auto px-1 py-1">
          <li
            v-for="user in store.users"
            :key="user.userId"
            class="rounded px-2 py-1.5 hover:bg-theme-border/40"
            data-testid="roles-user-item"
          >
            <div class="text-sm text-theme-text">{{ user.displayName || user.email || user.userId }}</div>
            <div v-if="user.email" class="text-[10px] font-mono text-theme-text-muted truncate">{{ user.email }}</div>
            <div class="mt-1 flex flex-wrap gap-1">
              <button
                v-for="role in store.roles"
                :key="role.id"
                type="button"
                class="rounded-full border px-2 py-0.5 text-[10px] transition-colors"
                :class="user.roles.some((r) => r.id === role.id)
                  ? 'border-transparent text-white'
                  : 'border-theme-border text-theme-text-muted hover:text-theme-text'"
                :style="user.roles.some((r) => r.id === role.id) ? { backgroundColor: role.color ?? '#5865F2' } : undefined"
                @click="toggleUserRole(user.userId, role.id, user.roles.some((r) => r.id === role.id))"
              >
                {{ role.name }}
              </button>
            </div>
          </li>
          <li v-if="store.users.length === 0" class="px-3 py-4 text-xs text-theme-text-muted">
            {{ ts('settings.users.empty', 'Nenhum usuário encontrado.') }}
          </li>
        </ul>
      </div>
    </aside>

    <!-- Right pane: role detail or users mode placeholder -->
    <section class="flex-1 min-w-0 overflow-y-auto p-5">
      <div v-if="store.error" class="mb-3 rounded border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">
        {{ store.error }}
      </div>

      <div v-if="mode === 'users'" class="text-sm text-theme-text-muted">
        {{ ts('settings.users.hint', 'Selecione o cargo na esquerda ou clique nos pills para conceder/revogar cargos por usuário.') }}
      </div>

      <div v-else-if="store.selectedRole && editDraft" class="flex flex-col gap-4">
        <header class="flex items-start justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="h-3 w-3 rounded-full" :style="{ backgroundColor: editDraft.color }" />
            <h3 class="text-base font-semibold text-theme-text">{{ store.selectedRole.name }}</h3>
            <span v-if="store.selectedRole.isSystem" class="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-amber-300">
              {{ ts('settings.roles.system', 'system') }}
            </span>
          </div>
          <div class="flex gap-2">
            <button
              type="button"
              class="rounded bg-theme-primary px-3 py-1 text-xs font-medium text-white transition-opacity disabled:opacity-40"
              :disabled="!isDirty || saving"
              @click="handleSave"
            >
              {{ ts('settings.roles.save', 'Salvar') }}
            </button>
            <button
              v-if="!store.selectedRole.isSystem"
              type="button"
              class="rounded border border-red-500/40 px-3 py-1 text-xs text-red-300 hover:bg-red-500/10"
              @click="handleDelete(store.selectedRole.id, store.selectedRole.name)"
            >
              <Trash2 :size="12" class="inline-block mr-1" />
              {{ ts('settings.roles.delete.button', 'Excluir') }}
            </button>
          </div>
        </header>

        <nav class="flex gap-1 border-b border-theme-border">
          <button
            v-for="tab in (['display','permissions','members'] as SubTab[])"
            :key="tab"
            type="button"
            class="px-3 py-1.5 text-xs font-medium border-b-2 transition-colors"
            :class="subTab === tab ? 'border-theme-primary text-theme-primary' : 'border-transparent text-theme-text-muted hover:text-theme-text'"
            :data-testid="`roles-subtab-${tab}`"
            @click="subTab = tab"
          >
            {{ ts(`settings.roles.subtabs.${tab}`, tab) }}
          </button>
        </nav>

        <!-- Display sub-tab -->
        <div v-if="subTab === 'display'" class="grid grid-cols-2 gap-3 max-w-lg">
          <label class="col-span-2 text-xs text-theme-text-muted">
            {{ ts('settings.roles.fields.name', 'Nome') }}
            <input
              v-model="editDraft.name"
              type="text"
              :disabled="store.selectedRole.isSystem"
              class="mt-1 w-full rounded border border-theme-border bg-theme-panel px-2 py-1.5 text-sm text-theme-text outline-none focus:border-theme-primary disabled:opacity-60"
            />
          </label>
          <label class="col-span-2 text-xs text-theme-text-muted">
            {{ ts('settings.roles.fields.description', 'Descrição') }}
            <textarea
              v-model="editDraft.description"
              rows="3"
              class="mt-1 w-full rounded border border-theme-border bg-theme-panel px-2 py-1.5 text-sm text-theme-text outline-none focus:border-theme-primary"
            />
          </label>
          <label class="text-xs text-theme-text-muted">
            {{ ts('settings.roles.fields.color', 'Cor') }}
            <input
              v-model="editDraft.color"
              type="color"
              class="mt-1 h-8 w-16 rounded border border-theme-border bg-theme-panel"
            />
          </label>
        </div>

        <!-- Permissions sub-tab -->
        <div v-else-if="subTab === 'permissions'" class="flex flex-col gap-3 max-w-2xl">
          <div v-if="store.selectedRole.isSystem" class="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">
            {{ ts('settings.roles.permissions.systemNote', 'Cargo do sistema tem todas as permissões (*) e não pode ser editado.') }}
          </div>
          <div v-for="category in store.categories" :key="category" class="rounded border border-theme-border bg-theme-bg/40 p-3">
            <h4 class="mb-2 text-xs font-semibold uppercase tracking-wider text-theme-text-muted">
              {{ ts(`settings.roles.permission.category.${category}`, category) }}
            </h4>
            <ul class="flex flex-col gap-1.5">
              <li
                v-for="perm in store.catalogByCategory[category]"
                :key="perm.slug"
                class="flex items-start gap-2"
              >
                <input
                  type="checkbox"
                  :id="`perm-${perm.slug}`"
                  :checked="editPermsDraft.has(perm.slug)"
                  :disabled="store.selectedRole.isSystem"
                  class="mt-0.5"
                  :data-testid="`perm-checkbox-${perm.slug}`"
                  @change="togglePerm(perm.slug)"
                />
                <label :for="`perm-${perm.slug}`" class="flex-1 cursor-pointer">
                  <span class="block text-sm text-theme-text">{{ ts(perm.labelKey, perm.slug) }}</span>
                  <span class="block text-[11px] text-theme-text-muted">{{ ts(perm.descriptionKey, '') }}</span>
                </label>
              </li>
            </ul>
          </div>
        </div>

        <!-- Members sub-tab -->
        <div v-else-if="subTab === 'members'" class="flex flex-col gap-2 max-w-2xl">
          <div class="flex items-center justify-between">
            <span class="text-xs text-theme-text-muted">
              {{ ts('settings.roles.members.count', '{count} membros').replace('{count}', String(store.selectedRole.memberCount)) }}
            </span>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded bg-theme-primary px-2 py-1 text-xs font-medium text-white hover:opacity-90"
              data-testid="roles-add-member-open"
              @click="addMemberOpen = true"
            >
              <UserPlus :size="12" />
              {{ ts('settings.roles.members.add', 'Adicionar') }}
            </button>
          </div>
          <ul class="flex flex-col divide-y divide-theme-border rounded border border-theme-border">
            <li
              v-for="member in (store.members[store.selectedRole.id] ?? [])"
              :key="member.userId"
              class="flex items-center justify-between p-2"
              data-testid="roles-member-row"
            >
              <div class="min-w-0">
                <div class="text-sm text-theme-text">{{ member.displayName || member.email || member.userId }}</div>
                <div v-if="member.email" class="text-[11px] font-mono text-theme-text-muted truncate">{{ member.email }}</div>
              </div>
              <button
                type="button"
                class="rounded p-1 text-theme-text-muted hover:bg-red-500/10 hover:text-red-300"
                :title="ts('settings.roles.members.remove', 'Remover')"
                @click="store.removeMember(store.selectedRole!.id, member.userId)"
              >
                <X :size="14" />
              </button>
            </li>
            <li v-if="(store.members[store.selectedRole.id] ?? []).length === 0" class="p-3 text-xs text-theme-text-muted">
              {{ ts('settings.roles.members.empty', 'Nenhum membro neste cargo.') }}
            </li>
          </ul>
        </div>
      </div>

      <div v-else class="text-sm text-theme-text-muted">
        {{ ts('settings.roles.selectHint', 'Selecione um cargo na esquerda ou crie um novo.') }}
      </div>
    </section>

    <!-- Create role modal -->
    <div v-if="createOpen" class="absolute inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="createOpen = false">
      <div class="w-full max-w-sm rounded-lg border border-theme-border bg-theme-panel p-4">
        <h3 class="mb-3 text-base font-semibold text-theme-text">{{ ts('settings.roles.create', 'Criar cargo') }}</h3>
        <label class="block text-xs text-theme-text-muted">
          {{ ts('settings.roles.fields.name', 'Nome') }}
          <input
            v-model="newRoleName"
            type="text"
            class="mt-1 w-full rounded border border-theme-border bg-theme-bg px-2 py-1.5 text-sm text-theme-text outline-none focus:border-theme-primary"
            data-testid="roles-create-name"
            @keyup.enter="handleCreateRole"
          />
        </label>
        <label class="mt-2 block text-xs text-theme-text-muted">
          {{ ts('settings.roles.fields.color', 'Cor') }}
          <input v-model="newRoleColor" type="color" class="mt-1 h-8 w-16 rounded border border-theme-border bg-theme-bg" />
        </label>
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded px-3 py-1 text-xs text-theme-text-muted hover:text-theme-text" @click="createOpen = false">
            {{ ts('common.cancel', 'Cancelar') }}
          </button>
          <button
            type="button"
            class="rounded bg-theme-primary px-3 py-1 text-xs font-medium text-white disabled:opacity-40"
            :disabled="!newRoleName.trim()"
            data-testid="roles-create-submit"
            @click="handleCreateRole"
          >
            {{ ts('settings.roles.create', 'Criar') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Add member modal -->
    <div v-if="addMemberOpen" class="absolute inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="addMemberOpen = false">
      <div class="w-full max-w-sm rounded-lg border border-theme-border bg-theme-panel p-4">
        <h3 class="mb-3 text-base font-semibold text-theme-text">{{ ts('settings.roles.members.add', 'Adicionar membro') }}</h3>
        <label class="block text-xs text-theme-text-muted">
          {{ ts('settings.roles.members.inputHint', 'E-mail ou user ID') }}
          <input
            v-model="newMemberInput"
            type="text"
            class="mt-1 w-full rounded border border-theme-border bg-theme-bg px-2 py-1.5 text-sm text-theme-text outline-none focus:border-theme-primary"
            data-testid="roles-add-member-input"
            @keyup.enter="handleAddMember"
          />
        </label>
        <div class="mt-4 flex justify-end gap-2">
          <button type="button" class="rounded px-3 py-1 text-xs text-theme-text-muted hover:text-theme-text" @click="addMemberOpen = false">
            {{ ts('common.cancel', 'Cancelar') }}
          </button>
          <button
            type="button"
            class="rounded bg-theme-primary px-3 py-1 text-xs font-medium text-white disabled:opacity-40"
            :disabled="!newMemberInput.trim()"
            data-testid="roles-add-member-submit"
            @click="handleAddMember"
          >
            {{ ts('settings.roles.members.add', 'Adicionar') }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
