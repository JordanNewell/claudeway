"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useState } from "react"

// Singleton pattern to prevent hydration mismatches
let browserQueryClient: QueryClient | undefined = undefined

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000,
        refetchOnWindowFocus: false,
      },
    },
  })
}

function getQueryClient() {
  if (typeof window === "undefined") {
    // Server: always create a new client
    return makeQueryClient()
  } else {
    // Browser: create client once and reuse
    if (!browserQueryClient) {
      browserQueryClient = makeQueryClient()
    }
    return browserQueryClient
  }
}

export function Providers({ children }: { children: React.ReactNode }) {
  // Note: useState avoids unnecessary re-renders, but we use the singleton
  const [queryClient] = useState(() => getQueryClient())

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
