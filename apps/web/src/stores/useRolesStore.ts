import { defineStore } from 'pinia'
import {
  rolesClient,
  type CreateRolePayload,
  type DirectoryUser,
  type PermissionCatalogEntry,
  type RoleMember,
  type RoleSummary,
  type UpdateRolePayload,
} from '../services/rolesClient'

type State = {
  roles: RoleSummary[]
  catalog: PermissionCatalogEntry[]
  users: DirectoryUser[]
  members: Record<string, RoleMember[]>
  selectedRoleId: string | null
  isLoading: boolean
  error: string | null
}

function setError(state: State, err: unknown) {
  state.error = err instanceof Error ? err.message : 'Unknown error'
}

export const useRolesStore = defineStore('roles', {
  state: (): State => ({
    roles: [],
    catalog: [],
    users: [],
    members: {},
    selectedRoleId: null,
    isLoading: false,
    error: null,
  }),
  getters: {
    selectedRole(state): RoleSummary | null {
      return state.roles.find((r) => r.id === state.selectedRoleId) ?? null
    },
    categories(state): string[] {
      return Array.from(new Set(state.catalog.map((c) => c.category)))
    },
    catalogByCategory(state): Record<string, PermissionCatalogEntry[]> {
      const out: Record<string, PermissionCatalogEntry[]> = {}
      for (const entry of state.catalog) {
        ;(out[entry.category] ??= []).push(entry)
      }
      return out
    },
  },
  actions: {
    async fetchAll() {
      this.isLoading = true
      this.error = null
      try {
        const [roles, catalog] = await Promise.all([
          rolesClient.listRoles(),
          rolesClient.getCatalog(),
        ])
        this.roles = roles
        this.catalog = catalog
        if (this.selectedRoleId === null && roles.length > 0) {
          this.selectedRoleId = roles[0].id
        }
      } catch (err) {
        setError(this, err)
      } finally {
        this.isLoading = false
      }
    },
    selectRole(roleId: string | null) {
      this.selectedRoleId = roleId
      if (roleId && !this.members[roleId]) {
        void this.fetchMembers(roleId)
      }
    },
    async fetchMembers(roleId: string) {
      try {
        this.members[roleId] = await rolesClient.listMembers(roleId)
      } catch (err) {
        setError(this, err)
      }
    },
    async createRole(payload: CreateRolePayload) {
      this.error = null
      try {
        const role = await rolesClient.createRole(payload)
        this.roles.push(role)
        this.roles.sort((a, b) => Number(b.isSystem) - Number(a.isSystem) || a.name.localeCompare(b.name))
        this.selectedRoleId = role.id
        return role
      } catch (err) {
        setError(this, err)
        throw err
      }
    },
    async updateRole(roleId: string, payload: UpdateRolePayload) {
      this.error = null
      try {
        const updated = await rolesClient.updateRole(roleId, payload)
        const idx = this.roles.findIndex((r) => r.id === roleId)
        if (idx >= 0) this.roles[idx] = updated
        return updated
      } catch (err) {
        setError(this, err)
        throw err
      }
    },
    async deleteRole(roleId: string) {
      this.error = null
      try {
        await rolesClient.deleteRole(roleId)
        this.roles = this.roles.filter((r) => r.id !== roleId)
        delete this.members[roleId]
        if (this.selectedRoleId === roleId) {
          this.selectedRoleId = this.roles[0]?.id ?? null
        }
      } catch (err) {
        setError(this, err)
        throw err
      }
    },
    async addMember(roleId: string, body: { userId?: string; email?: string }) {
      this.error = null
      try {
        const member = await rolesClient.addMember(roleId, body)
        const list = this.members[roleId] ?? []
        if (!list.find((m) => m.userId === member.userId)) {
          list.push(member)
          this.members[roleId] = list.sort((a, b) =>
            (a.displayName ?? a.email ?? a.userId).localeCompare(
              b.displayName ?? b.email ?? b.userId,
            ),
          )
        }
        const role = this.roles.find((r) => r.id === roleId)
        if (role) role.memberCount = (role.memberCount ?? 0) + 1
        return member
      } catch (err) {
        setError(this, err)
        throw err
      }
    },
    async removeMember(roleId: string, userId: string) {
      this.error = null
      try {
        await rolesClient.removeMember(roleId, userId)
        this.members[roleId] = (this.members[roleId] ?? []).filter((m) => m.userId !== userId)
        const role = this.roles.find((r) => r.id === roleId)
        if (role) role.memberCount = Math.max(0, (role.memberCount ?? 0) - 1)
      } catch (err) {
        setError(this, err)
        throw err
      }
    },
    async fetchUsers(query: string | null = null) {
      this.error = null
      try {
        this.users = await rolesClient.listUsers(query)
      } catch (err) {
        setError(this, err)
      }
    },
    async setUserRoles(userId: string, add: string[], remove: string[]) {
      this.error = null
      try {
        const updated = await rolesClient.updateUserRoles(userId, { add, remove })
        const idx = this.users.findIndex((u) => u.userId === userId)
        if (idx >= 0) this.users[idx] = updated
        else this.users.push(updated)
        for (const roleId of add) {
          const role = this.roles.find((r) => r.id === roleId)
          if (role) role.memberCount = (role.memberCount ?? 0) + 1
        }
        for (const roleId of remove) {
          const role = this.roles.find((r) => r.id === roleId)
          if (role) role.memberCount = Math.max(0, (role.memberCount ?? 0) - 1)
        }
        return updated
      } catch (err) {
        setError(this, err)
        throw err
      }
    },
  },
})
