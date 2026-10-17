// TypeScript types matching Tractum backend

export type TenantTier = "free" | "pro" | "enterprise"
export type TenantStatus = "active" | "suspended" | "cancelled"
export type AgentStatus = "deploying" | "running" | "stopped" | "error"
export type InvoiceStatus = "draft" | "pending" | "paid" | "failed" | "cancelled"

export interface Tenant {
  id: string
  name: string
  email: string
  tier: TenantTier
  status: TenantStatus
  stripe_customer_id?: string
  stripe_subscription_id?: string
  created_at: string
  updated_at: string
  max_agents: number
  max_messages_per_month: number
}

export interface Agent {
  id: string
  tenant_id: string
  name: string
  template_id: string
  status: AgentStatus
  error_message?: string
  swarm_id?: string
  created_at: string
  updated_at: string
  last_active_at?: string
}

export interface Template {
  id: string
  name: string
  display_name: string
  description: string
  config: string
  category: string
  tags: string[]
  is_public: boolean
  price_id?: string
  created_at: string
  updated_at: string
}

export interface UsageRecord {
  id: string
  tenant_id: string
  agent_id: string
  messages: number
  tokens: number
  duration_seconds: number
  recorded_at: string
}

export interface Invoice {
  id: string
  tenant_id: string
  invoice_number: string
  amount: number
  currency: string
  period_start: string
  period_end: string
  status: InvoiceStatus
  stripe_invoice_id?: string
  stripe_payment_intent_id?: string
  created_at: string
  paid_at?: string
}

export interface Usage {
  tenant_id: string
  period_start: string
  period_end: string
  messages: number
  tokens: number
}

// Request types
export interface CreateTenantRequest {
  name: string
  email: string
  tier?: TenantTier
}

export interface DeployAgentRequest {
  name: string
  template_id: string
  config?: Record<string, unknown>
}

export interface SendMessageRequest {
  message: string
  user_id?: string
}

export interface CreateTemplateRequest {
  name: string
  display_name: string
  description: string
  config: Record<string, unknown>
  category?: string
  tags?: string[]
  is_public?: boolean
}
