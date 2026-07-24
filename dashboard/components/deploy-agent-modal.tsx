"use client"

import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/lib/api-client"
import { useAppStore } from "@/lib/store"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { X, Plus, Trash2 } from "lucide-react"

interface AgentConfig {
  name: string
  role: string
  instructions: string
}

// Predefined agent templates
const AGENT_TEMPLATES: Record<string, { name: string; role: string; instructions: string }[]> = {
  "research-swarm": [
    {
      name: "Researcher",
      role: "Lead Research Analyst",
      instructions: "You analyze problems thoroughly and provide detailed insights.",
    },
    {
      name: "Critic",
      role: "Critical Reviewer",
      instructions: "You evaluate ideas for strengths, weaknesses, and potential risks.",
    },
    {
      name: "Synthesizer",
      role: "Synthesis Expert",
      instructions: "You combine multiple perspectives into a coherent final recommendation.",
    },
  ],
  "task-coordinator": [
    {
      name: "Researcher",
      role: "Research Specialist",
      instructions: "You gather and analyze information thoroughly.",
    },
    {
      name: "Analyst",
      role: "Technical Analyst",
      instructions: "You provide technical analysis and recommendations.",
    },
    {
      name: "Writer",
      role: "Technical Writer",
      instructions: "You synthesize information into clear, structured documentation.",
    },
  ],
}

export function DeployAgentModal() {
  const queryClient = useQueryClient()
  const { deployAgentOpen, setDeployAgentOpen } = useAppStore()

  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [templateId, setTemplateId] = useState("research-swarm")
  const [agents, setAgents] = useState<AgentConfig[]>(AGENT_TEMPLATES["research-swarm"])
  const [showCustomAgent, setShowCustomAgent] = useState(false)

  const deployMutation = useMutation({
    mutationFn: (data: { name: string; description: string; agents: AgentConfig[] }) =>
      apiClient.deployAgent({
        name: data.name,
        description: data.description,
        agents: data.agents,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] })
      setDeployAgentOpen(false)
      setName("")
      setDescription("")
      setAgents([])
      setTemplateId("research-swarm")
    },
  })

  // Load template agents when template changes
  const handleTemplateChange = (template: string) => {
    setTemplateId(template)
    if (AGENT_TEMPLATES[template]) {
      setAgents([...AGENT_TEMPLATES[template]])
    }
  }

  // Add custom agent
  const addAgent = () => {
    setAgents([...agents, { name: "", role: "", instructions: "" }])
    setShowCustomAgent(true)
  }

  // Remove agent
  const removeAgent = (index: number) => {
    setAgents(agents.filter((_, i) => i !== index))
  }

  // Update agent
  const updateAgent = (index: number, field: keyof AgentConfig, value: string) => {
    const newAgents = [...agents]
    newAgents[index][field] = value
    setAgents(newAgents)
  }

  if (!deployAgentOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-2xl p-6 relative max-h-[90vh] overflow-y-auto">
        <button
          onClick={() => setDeployAgentOpen(false)}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">Deploy Agent Swarm</h2>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (agents.length === 0) {
              return
            }
            deployMutation.mutate({ name, description, agents })
          }}
          className="space-y-4"
        >
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Swarm Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Research Swarm"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="A swarm for research and analysis tasks"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              rows={2}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Template
            </label>
            <select
              value={templateId}
              onChange={(e) => handleTemplateChange(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="research-swarm">Research Swarm (3 agents)</option>
              <option value="task-coordinator">Task Coordinator (3 specialists)</option>
            </select>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Agents ({agents.length})
              </label>
              <button
                type="button"
                onClick={addAgent}
                className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
              >
                <Plus className="w-4 h-4" />
                Add Agent
              </button>
            </div>

            <div className="space-y-3">
              {agents.map((agent, index) => (
                <div key={index} className="p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-800">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Agent #{index + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeAgent(index)}
                      className="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="space-y-2">
                    <input
                      type="text"
                      value={agent.name}
                      onChange={(e) => updateAgent(index, "name", e.target.value)}
                      placeholder="Agent name"
                      className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      required
                    />
                    <input
                      type="text"
                      value={agent.role}
                      onChange={(e) => updateAgent(index, "role", e.target.value)}
                      placeholder="Agent role"
                      className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      required
                    />
                    <textarea
                      value={agent.instructions}
                      onChange={(e) => updateAgent(index, "instructions", e.target.value)}
                      placeholder="Agent instructions"
                      className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      rows={2}
                      required
                    />
                  </div>
                </div>
              ))}
            </div>

            {agents.length === 0 && (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                Select a template or add agents manually
              </div>
            )}
          </div>

          {deployMutation.error && (
            <div className="p-3 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg text-sm">
              {(deployMutation.error as Error).message || "Failed to deploy agent swarm"}
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setDeployAgentOpen(false)}
              className="flex-1"
              disabled={deployMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              className="flex-1"
              disabled={deployMutation.isPending || agents.length === 0}
            >
              {deployMutation.isPending ? "Deploying..." : "Deploy Swarm"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
