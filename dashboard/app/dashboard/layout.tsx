"use client"

import { Sidebar } from "@/components/sidebar"
import { Header } from "@/components/header"
import { DeployAgentModal } from "@/components/deploy-agent-modal"
import { useAppStore } from "@/lib/store"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const sidebarOpen = useAppStore((state) => state.sidebarOpen)

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Sidebar />
      <div
        className={`transition-all duration-300 ${
          sidebarOpen ? "ml-64" : "ml-16"
        }`}
      >
        <Header />
        <main className="p-6">{children}</main>
      </div>
      <DeployAgentModal />
    </div>
  )
}
