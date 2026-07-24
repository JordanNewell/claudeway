import Link from "next/link"

export default function DocsPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
      <div className="container mx-auto px-4 py-16">
        <div className="max-w-4xl mx-auto">
          <div className="mb-8">
            <Link
              href="/"
              className="text-blue-600 dark:text-blue-400 hover:underline"
            >
              &larr; Back to Home
            </Link>
          </div>

          <h1 className="text-5xl font-bold text-gray-900 dark:text-white mb-8">
            Claudeway Documentation
          </h1>

          <div className="space-y-8">
            <section className="bg-white dark:bg-gray-800 p-8 rounded-xl shadow-lg">
              <h2 className="text-3xl font-semibold text-gray-900 dark:text-white mb-4">
                Getting Started
              </h2>
              <p className="text-gray-600 dark:text-gray-400 mb-4">
                Claudeway is a Claude-native agent infrastructure platform built on top of Claude-Flow orchestration.
              </p>
              <ul className="list-disc list-inside text-gray-600 dark:text-gray-400 space-y-2">
                <li>Deploy and manage Claude agents</li>
                <li>Multi-tenant support with billing</li>
                <li>Pre-configured agent templates</li>
                <li>Real-time monitoring and logging</li>
              </ul>
            </section>

            <section className="bg-white dark:bg-gray-800 p-8 rounded-xl shadow-lg">
              <h2 className="text-3xl font-semibold text-gray-900 dark:text-white mb-4">
                Quick Start
              </h2>
              <div className="bg-gray-900 text-gray-100 p-4 rounded-lg font-mono text-sm">
                <p># Start the infrastructure</p>
                <p>docker-compose up -d</p>
                <p className="mt-2"># Start the API</p>
                <p>cd api && uvicorn main:app</p>
                <p className="mt-2"># Start the dashboard</p>
                <p>cd dashboard && npm run dev</p>
              </div>
            </section>

            <section className="bg-white dark:bg-gray-800 p-8 rounded-xl shadow-lg">
              <h2 className="text-3xl font-semibold text-gray-900 dark:text-white mb-4">
                API Endpoints
              </h2>
              <ul className="space-y-2 text-gray-600 dark:text-gray-400">
                <li><code className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">GET /health</code> - Health check</li>
                <li><code className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">GET /api/v1/agents</code> - List agents</li>
                <li><code className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">POST /api/v1/agents</code> - Create agent</li>
                <li><code className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">GET /api/v1/tenants</code> - List tenants</li>
              </ul>
            </section>
          </div>
        </div>
      </div>
    </main>
  )
}
