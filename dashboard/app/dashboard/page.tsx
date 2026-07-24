"use client"

import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api-client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Bot, Activity, Zap } from "lucide-react"

export default function DashboardPage() {
  const { data: agents } = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiClient.getAgents(),
  })

  const { data: runtimeStatus } = useQuery({
    queryKey: ["runtime-status"],
    queryFn: () => apiClient.getRuntimeStatus(),
    refetchInterval: 5000, // Poll every 5 seconds
  })

  const runningAgents = agents?.filter((a: any) => a.status === "running").length || 0
  const totalAgents = agents?.length || 0
  const swarmCount = runtimeStatus?.swarm_count || 0

  const stats = [
    {
      title: "Running Agents",
      value: runningAgents,
      total: totalAgents,
      icon: Bot,
      color: "text-blue-600",
      bgColor: "bg-blue-100 dark:bg-blue-900",
    },
    {
      title: "Active Swarms",
      value: swarmCount,
      total: swarmCount,
      icon: Activity,
      color: "text-green-600",
      bgColor: "bg-green-100 dark:bg-green-900",
    },
    {
      title: "Runtime Status",
      value: runtimeStatus?.running ? "Running" : "Stopped",
      total: runtimeStatus?.running ? "System healthy" : "System offline",
      icon: Zap,
      color: runtimeStatus?.running ? "text-green-600" : "text-red-600",
      bgColor: runtimeStatus?.running ? "bg-green-100 dark:bg-green-900" : "bg-red-100 dark:bg-red-900",
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <p className="text-gray-600 dark:text-gray-400">Claude-native agent orchestration platform</p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <Card key={stat.title}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-gray-600 dark:text-gray-400">
                  {stat.title}
                </CardTitle>
                <div className={`p-2 rounded-lg ${stat.bgColor}`}>
                  <Icon className={`w-4 h-4 ${stat.color}`} />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-gray-900 dark:text-white">{stat.value}</div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {stat.total}
                </p>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Recent Agents */}
      <Card>
        <CardHeader>
          <CardTitle>Deployed Swarms</CardTitle>
        </CardHeader>
        <CardContent>
          {agents && agents.length > 0 ? (
            <div className="space-y-4">
              {agents.slice(0, 5).map((agent: any) => (
                <div key={agent.id} className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">{agent.name}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{agent.description}</p>
                  </div>
                  <span
                    className={`px-2 py-1 text-xs rounded-full ${
                      agent.status === "running"
                        ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                        : agent.status === "error"
                        ? "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
                        : "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
                    }`}
                  >
                    {agent.status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-gray-500 dark:text-gray-400 mb-4">No swarms deployed yet</p>
              <p className="text-sm text-gray-400 dark:text-gray-500">
                Deploy your first swarm to get started
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
