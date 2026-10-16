import { create } from "zustand"
import type { Tenant } from "./api-client"

interface AppState {
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
  deployAgentOpen: boolean
  setDeployAgentOpen: (open: boolean) => void
  createTenantOpen: boolean
  setCreateTenantOpen: (open: boolean) => void
  currentTenant: Tenant | null
  setCurrentTenant: (tenant: Tenant | null) => void
}

export const useAppStore = create<AppState>((set) => ({
  sidebarOpen: true,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  deployAgentOpen: false,
  setDeployAgentOpen: (open) => set({ deployAgentOpen: open }),
  createTenantOpen: false,
  setCreateTenantOpen: (open) => set({ createTenantOpen: open }),
  currentTenant: null,
  setCurrentTenant: (tenant) => set({ currentTenant: tenant }),
}))
