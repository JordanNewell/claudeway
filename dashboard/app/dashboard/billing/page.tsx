"use client"

import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api-client"
import { useAppStore } from "@/lib/store"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { DollarSign, FileText } from "lucide-react"

export default function BillingPage() {
  const currentTenant = useAppStore((state) => state.currentTenant)

  const { data: usage } = useQuery({
    queryKey: ["usage", currentTenant?.id],
    queryFn: () => apiClient.getUsage(currentTenant!.id),
    enabled: !!currentTenant,
  })

  const { data: invoices } = useQuery({
    queryKey: ["invoices", currentTenant?.id],
    queryFn: () => apiClient.getInvoices(currentTenant!.id),
    enabled: !!currentTenant,
  })

  const getInvoiceStatusColor = (status: string) => {
    switch (status) {
      case "paid":
        return "success"
      case "pending":
        return "warning"
      case "failed":
        return "destructive"
      default:
        return "secondary"
    }
  }

  if (!currentTenant) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <DollarSign className="w-16 h-16 text-gray-400 mb-4" />
          <p className="text-lg font-medium text-gray-900 dark:text-white">Select a tenant first</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Billing</h1>
        <p className="text-gray-600 dark:text-gray-400">Usage and invoices for {currentTenant.name}</p>
      </div>

      {/* Usage Stats */}
      <div className="grid gap-6 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 dark:text-gray-400">
              Messages
            </CardTitle>
            <FileText className="w-4 h-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {usage?.messages?.toLocaleString() || 0}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">This month</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 dark:text-gray-400">
              Tokens
            </CardTitle>
            <FileText className="w-4 h-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {usage?.tokens?.toLocaleString() || 0}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">This month</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-gray-600 dark:text-gray-400">
              Limit
            </CardTitle>
            <DollarSign className="w-4 h-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {currentTenant.max_messages_per_month === -1
                ? "Unlimited"
                : currentTenant.max_messages_per_month.toLocaleString()}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">Monthly limit</p>
          </CardContent>
        </Card>
      </div>

      {/* Invoices */}
      <Card>
        <CardHeader>
          <CardTitle>Invoices</CardTitle>
        </CardHeader>
        <CardContent>
          {invoices && invoices.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invoice</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoices.map((invoice) => (
                  <TableRow key={invoice.id}>
                    <TableCell className="font-medium">{invoice.invoice_number}</TableCell>
                    <TableCell>
                      {new Date(invoice.period_start).toLocaleDateString()} -{" "}
                      {new Date(invoice.period_end).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      {invoice.currency === "usd" ? "$" : ""}{invoice.amount.toFixed(2)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={getInvoiceStatusColor(invoice.status)}>{invoice.status}</Badge>
                    </TableCell>
                    <TableCell>{new Date(invoice.created_at).toLocaleDateString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-center text-gray-500 dark:text-gray-400 py-8">No invoices yet</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
