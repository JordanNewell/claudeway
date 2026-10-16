import axios from "axios"

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
})

export interface AgentConfig {
  name: string
  role: string
  instructions: string
}

export interface Swarm {
  swarm_id?: string
  id?: string
  name?: string
  swarm_name?: string
  status?: string
  role?: string
  agent_count?: number
  created_at?: string
  last_activity?: string
}

export interface RuntimeStatus {
  swarm_count: number
  agent_count: number
  [key: string]: unknown
}

export interface Tenant {
  id: string
  name: string
  email: string
  tier: string
  status: string
  max_agents: number
  max_messages_per_month: number
  created_at: string
}

export interface Usage {
  messages: number
  tokens: number
}

export interface Invoice {
  id: string
  invoice_number: string
  period_start: string
  period_end: string
  amount: number
  currency: string
  status: string
  created_at: string
}

export interface Template {
  id: string
  display_name: string
  description: string
  category: string
  tags: string[]
}

export const apiClient = {
  getAgents(): Promise<Swarm[]> {
    return api.get<Swarm[]>("/v1/agents/").then((res) => res.data)
  },

  getRuntimeStatus(): Promise<RuntimeStatus> {
    return api.get<RuntimeStatus>("/v1/agents/status").then((res) => res.data)
  },

  deployAgent(data: { name: string; description: string; agents: AgentConfig[] }) {
    return api.post("/v1/agents/", data).then((res) => res.data)
  },

  submitTask(swarmId: string, data: { task_description: string }) {
    return api.post(`/v1/agents/${swarmId}/task`, data).then((res) => res.data)
  },

  getTenants(): Promise<Tenant[]> {
    return api.get<Tenant[]>("/v1/tenants/").then((res) => res.data)
  },

  getUsage(tenantId: string): Promise<Usage> {
    return api.get<Usage>(`/v1/billing/${tenantId}/usage`).then((res) => res.data)
  },

  getInvoices(tenantId: string): Promise<Invoice[]> {
    return api.get<Invoice[]>(`/v1/billing/${tenantId}/invoices`).then((res) => res.data)
  },

  getTemplates(): Promise<Template[]> {
    return api.get<Template[]>("/v1/templates/").then((res) => res.data)
  },
}
