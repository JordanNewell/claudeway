"use client"

import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/lib/api-client"
import { useAppStore } from "@/lib/store"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Bot, Plus, Send } from "lucide-react"

export default function AgentsPage() {
  const queryClient = useQueryClient()
  const setDeployAgentOpen = useAppStore((state) => state.setDeployAgentOpen)

  const { data: agents, isLoading } = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiClient.getAgents(),
  })

  const { data: runtimeStatus } = useQuery({
    queryKey: ["runtime-status"],
    queryFn: () => apiClient.getRuntimeStatus(),
    refetchInterval: 5000, // Poll every 5 seconds
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Agent Swarms</h1>
          <p className="text-gray-600 dark:text-gray-400">
            {runtimeStatus?.swarm_count || 0} swarm{runtimeStatus?.swarm_count !== 1 ? "s" : ""} deployed
            {runtimeStatus?.agent_count && ` · ${runtimeStatus.agent_count} agents running`}
          </p>
        </div>
        <Button onClick={() => setDeployAgentOpen(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Deploy Swarm
        </Button>
      </div>

      {isLoading ? (
        <p>Loading...</p>
      ) : agents && agents.length > 0 ? (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent: any) => (
            <Card key={agent.swarm_id || agent.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <CardTitle className="text-lg">{agent.name || agent.swarm_name}</CardTitle>
                  <Badge variant="success">{agent.status || "running"}</Badge>
                </div>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {agent.swarm_id && `Swarm ID: ${agent.swarm_id.slice(0, 8)}...`}
                  {agent.role && <span>{agent.role}</span>}
                </p>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                  {agent.agent_count !== undefined && (
                    <p>Agents: {agent.agent_count}</p>
                  )}
                  {agent.created_at && (
                    <p>Created: {new Date(agent.created_at).toLocaleDateString()}</p>
                  )}
                  {agent.last_activity && (
                    <p>Last active: {new Date(agent.last_activity).toLocaleString()}</p>
                  )}
                </div>
                <div className="flex gap-2 mt-4">
                  {agent.swarm_id && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        const task = prompt("Enter task description:")
                        if (task) {
                          apiClient.submitTask(agent.swarm_id, { task_description: task })
                            .then(() => queryClient.invalidateQueries({ queryKey: ["agents"] }))
                        }
                      }}
                    >
                      <Send className="w-3 h-3 mr-1" />
                      Send Task
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Bot className="w-16 h-16 text-gray-400 mb-4" />
            <p className="text-lg font-medium text-gray-900 dark:text-white mb-2">No swarms deployed</p>
            <p className="text-gray-500 dark:text-gray-400 mb-4">Deploy your first agent swarm to get started</p>
            <Button onClick={() => setDeployAgentOpen(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Deploy Swarm
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
