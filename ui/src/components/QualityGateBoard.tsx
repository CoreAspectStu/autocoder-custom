import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bug, Link2, Filter } from 'lucide-react'

// Types for DevLayer Quality Gate
interface DevLayerCard {
  id: string
  uat_card_id?: string
  dev_card_id?: string
  severity?: 'Critical' | 'High' | 'Medium' | 'Low'
  category?: 'UI' | 'Logic' | 'API' | 'Performance' | 'A11Y'
  triage_notes?: string
  triaged_by?: string
  triaged_at?: string
  approved_by?: string
  approved_at?: string
  status: 'triage' | 'approved_for_dev' | 'assigned' | 'monitoring'
  title: string
  description: string
  evidence?: {
    scenario_id: string
    error_message: string
    steps_to_reproduce: string[]
  }
  created_at: string
  updated_at: string
}

const severityColors = {
  Critical: 'bg-red-500 text-white',
  High: 'bg-yellow-500 text-black',
  Medium: 'bg-green-500 text-white',
  Low: 'bg-gray-400 text-black'
}

const severityEmojis = {
  Critical: '🔴',
  High: '🟡',
  Medium: '🟢',
  Low: '⚪'
}

const categoryColors = {
  UI: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  Logic: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  API: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  Performance: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200',
  A11Y: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200'
}

const statusColumns = {
  triage: 'Triage',
  approved_for_dev: 'Approved for Dev',
  assigned: 'Assigned',
  monitoring: 'Monitoring'
}

interface QualityGateBoardProps {
  project?: string
}

export function QualityGateBoard({ project: _project }: QualityGateBoardProps) {
  const queryClient = useQueryClient()
  const [selectedStatus, setSelectedStatus] = useState<string | null>(null)
  const [selectedCard, setSelectedCard] = useState<DevLayerCard | null>(null)
  const [showTriageModal, setShowTriageModal] = useState(false)
  const [showApproveModal, setShowApproveModal] = useState(false)

  // Fetch board stats
  useQuery<Record<string, number>>({
    queryKey: ['quality', 'stats'],
    queryFn: async () => {
      const res = await fetch('/api/quality/stats')
      if (!res.ok) throw new Error('Failed to fetch stats')
      return res.json()
    },
    refetchInterval: 5000
  })

  // Fetch cards by status
  useQuery<DevLayerCard[]>({
    queryKey: ['quality', 'cards', selectedStatus],
    queryFn: async () => {
      if (!selectedStatus) return []
      const res = await fetch(`/api/quality/cards?status=${selectedStatus}`)
      if (!res.ok) throw new Error('Failed to fetch cards')
      return res.json()
    },
    enabled: !!selectedStatus,
    refetchInterval: 5000
  })

  // Fetch all cards (for counts)
  const { data: allCards = [] } = useQuery<DevLayerCard[]>({
    queryKey: ['quality', 'all-cards'],
    queryFn: async () => {
      const cards: DevLayerCard[] = []
      for (const status of Object.keys(statusColumns)) {
        const res = await fetch(`/api/quality/cards?status=${status}`)
        if (res.ok) {
          const statusCards = await res.json()
          cards.push(...statusCards)
        }
      }
      return cards
    },
    refetchInterval: 5000
  })

  // Triage mutation
  const triageMutation = useMutation({
    mutationFn: async ({ cardId, severity, category, notes, triagedBy }: {
      cardId: string
      severity: string
      category: string
      notes: string
      triagedBy: string
    }) => {
      const res = await fetch(`/api/quality/triage/${cardId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          severity,
          category,
          triage_notes: notes,
          triaged_by: triagedBy
        })
      })
      if (!res.ok) throw new Error('Failed to triage card')
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quality'] })
      setShowTriageModal(false)
      setSelectedCard(null)
    }
  })

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: async ({ cardId, assignee }: {
      cardId: string
      assignee?: string
    }) => {
      const res = await fetch(`/api/quality/approve/${cardId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          assignee: assignee || null
        })
      })
      if (!res.ok) throw new Error('Failed to approve card')
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quality'] })
      setShowApproveModal(false)
      setSelectedCard(null)
    }
  })

  return (
    <div className="p-6 bg-white dark:bg-gray-800 rounded-lg">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Bug className="w-6 h-6" />
            DevLayer Quality Gate
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Triage and prioritize bugs before sending to Dev
          </p>
        </div>
        <div className="flex gap-2">
          <button className="px-3 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 flex items-center gap-1">
            <Filter className="w-4 h-4" />
            Filter
          </button>
        </div>
      </div>

      {/* Columns */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {Object.entries(statusColumns).map(([status, title]) => {
          const statusCards = allCards.filter((c) => c.status === status)
          return (
            <div
              key={status}
              className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${
                selectedStatus === status
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
              onClick={() => setSelectedStatus(selectedStatus === status ? null : status)}
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-gray-800 dark:text-gray-200">{title}</h3>
                <span className="bg-gray-200 dark:bg-gray-700 px-2 py-1 rounded-full text-sm">
                  {statusCards.length}
                </span>
              </div>

              {/* Cards in this column */}
              <div className="space-y-2">
                {statusCards.slice(0, 5).map((card) => (
                  <div
                    key={card.id}
                    onClick={(e) => {
                      e.stopPropagation()
                      setSelectedCard(card)
                    }}
                    className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 hover:shadow-md transition-all cursor-pointer"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        {card.severity && (
                          <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium mb-2 ${severityColors[card.severity]}`}>
                            {severityEmojis[card.severity]} {card.severity}
                          </span>
                        )}
                        <h4 className="font-medium text-sm text-gray-900 dark:text-white">{card.title}</h4>
                        {card.category && (
                          <span className={`inline-block px-2 py-0.5 rounded text-xs ${categoryColors[card.category]}`}>
                            {card.category}
                          </span>
                        )}
                      </div>
                      {card.uat_card_id && (
                        <Link2 className="w-4 h-4 text-blue-500" />
                      )}
                    </div>

                    {card.evidence && (
                      <p className="text-xs text-gray-600 dark:text-gray-400 mt-2 truncate">
                        {card.evidence.error_message}
                      </p>
                    )}
                  </div>
                ))}

                {statusCards.length > 5 && (
                  <p className="text-xs text-gray-500 text-center py-2">
                    +{statusCards.length - 5} more
                  </p>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Card Detail Panel */}
      {selectedCard && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold">Card Details</h3>
              <button
                onClick={() => setSelectedCard(null)}
                className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Title
                </label>
                <p className="text-gray-900 dark:text-white">{selectedCard.title}</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Status
                </label>
                <span className="inline-block px-2 py-1 rounded text-sm bg-gray-100 dark:bg-gray-700">
                  {statusColumns[selectedCard.status]}
                </span>
              </div>

              {selectedCard.severity && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Severity
                  </label>
                  <span className={`inline-block px-2 py-1 rounded text-sm ${severityColors[selectedCard.severity]}`}>
                    {severityEmojis[selectedCard.severity]} {selectedCard.severity}
                  </span>
                </div>
              )}

              {selectedCard.category && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Category
                  </label>
                  <span className={`inline-block px-2 py-1 rounded text-sm ${categoryColors[selectedCard.category]}`}>
                    {selectedCard.category}
                  </span>
                </div>
              )}

              {selectedCard.evidence && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Error
                  </label>
                  <p className="text-sm text-red-600 dark:text-red-400">{selectedCard.evidence.error_message}</p>
                </div>
              )}

              {selectedCard.evidence?.steps_to_reproduce && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Steps to Reproduce
                  </label>
                  <ol className="text-sm text-gray-600 dark:text-gray-400 list-decimal list-inside">
                    {selectedCard.evidence.steps_to_reproduce.map((step, i) => (
                      <li key={i}>{step}</li>
                    ))}
                  </ol>
                </div>
              )}

              {/* Action Buttons */}
              {selectedCard.status === 'triage' && (
                <div className="flex gap-2 pt-4 border-t">
                  <button
                    onClick={() => { setShowTriageModal(true); setSelectedCard(null) }}
                    className="flex-1 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
                  >
                    Triage Bug
                  </button>
                </div>
              )}

              {selectedCard.status === 'approved_for_dev' && selectedCard.severity && (
                <div className="flex gap-2 pt-4 border-t">
                  <button
                    onClick={() => { setShowApproveModal(true); setSelectedCard(null) }}
                    className="flex-1 px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
                  >
                    Approve for Dev
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Triage Modal */}
      {showTriageModal && selectedCard && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-xl font-bold mb-4">Triage Bug</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Severity
                </label>
                <select
                  id="severity-select"
                  className="w-full border rounded px-3 py-2 dark:bg-gray-700 dark:border-gray-600"
                >
                  <option value="">Select severity...</option>
                  <option value="Critical">🔴 Critical</option>
                  <option value="High">🟡 High</option>
                  <option value="Medium">🟢 Medium</option>
                  <option value="Low">⚪ Low</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Category
                </label>
                <select
                  id="category-select"
                  className="w-full border rounded px-3 py-2 dark:bg-gray-700 dark:border-gray-600"
                >
                  <option value="">Select category...</option>
                  <option value="UI">UI</option>
                  <option value="Logic">Logic</option>
                  <option value="API">API</option>
                  <option value="Performance">Performance</option>
                  <option value="A11Y">Accessibility</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Triage Notes
                </label>
                <textarea
                  id="triage-notes"
                  className="w-full border rounded px-3 py-2 dark:bg-gray-700 dark:border-gray-600"
                  rows={3}
                  placeholder="Add notes about this bug..."
                />
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => {
                    const severity = (document.getElementById('severity-select') as HTMLSelectElement).value
                    const category = (document.getElementById('category-select') as HTMLSelectElement).value
                    const notes = (document.getElementById('triage-notes') as HTMLTextAreaElement).value

                    if (severity && category) {
                      triageMutation.mutate({
                        cardId: selectedCard.id,
                        severity,
                        category,
                        notes,
                        triagedBy: 'user@example.com'
                      })
                    }
                  }}
                  className="flex-1 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
                  disabled={triageMutation.isPending}
                >
                  {triageMutation.isPending ? 'Saving...' : 'Save'}
                </button>
                <button
                  onClick={() => { setShowTriageModal(false); setSelectedCard(null) }}
                  className="px-4 py-2 border rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Approve Modal */}
      {showApproveModal && selectedCard && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-xl font-bold mb-4">Approve for Dev</h3>

            <div className="space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Approve this bug to be sent to the Dev team?
              </p>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Assignee (optional)
                </label>
                <input
                  type="text"
                  id="assignee-input"
                  className="w-full border rounded px-3 py-2 dark:bg-gray-700 dark:border-gray-600"
                  placeholder="developer@example.com"
                />
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => {
                    const assignee = (document.getElementById('assignee-input') as HTMLInputElement).value

                    approveMutation.mutate({
                      cardId: selectedCard.id,
                      assignee: assignee || undefined
                    })
                  }}
                  className="flex-1 px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
                  disabled={approveMutation.isPending}
                >
                  {approveMutation.isPending ? 'Approving...' : 'Approve'}
                </button>
                <button
                  onClick={() => { setShowApproveModal(false); setSelectedCard(null) }}
                  className="px-4 py-2 border rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
