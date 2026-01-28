import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { X, Play, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'

interface UATTriggerModalProps {
  project: string
  onClose: () => void
  onSuccess?: (cycleId: string) => void
}

export function UATTriggerModal({ project, onClose, onSuccess }: UATTriggerModalProps) {
  const [force, setForce] = useState(false)
  const [triggerSuccess, setTriggerSuccess] = useState(false)
  const [cycleId, setCycleId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Trigger mutation
  const triggerMutation = useMutation({
    mutationFn: async () => {
      setError(null)
      const payload = {
        project_name: project,
        force
      }
      console.log('[UATTrigger] Fetching /api/uat/trigger with payload:', payload)

      const res = await fetch('/api/uat/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(errorData.detail || `Failed to trigger UAT: ${res.statusText}`)
      }

      return res.json()
    },
    onSuccess: (data) => {
      setCycleId(data.cycle_id)
      setTriggerSuccess(true)
      onSuccess?.(data.cycle_id)
    },
    onError: (error: Error) => {
      console.error('[UATTrigger] Mutation error:', error)
      setError(error.message)
    },
  })

  const handleRunTests = () => {
    triggerMutation.mutate()
  }

  const handleClose = () => {
    if (triggerMutation.isPending) return // Don't allow closing while loading
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg max-w-md w-full">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Play className="w-5 h-5 text-purple-600" />
              Run UAT Tests
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Project: <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">{project}</code>
            </p>
          </div>
          {!triggerMutation.isPending && (
            <button
              onClick={handleClose}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Error state */}
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h4 className="font-medium text-red-900 dark:text-red-200 mb-1">Error Starting Tests</h4>
                  <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
                </div>
                <button
                  onClick={() => setError(null)}
                  className="text-red-600 hover:text-red-800 dark:text-red-400"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* Success state */}
          {triggerSuccess && (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h4 className="font-medium text-green-900 dark:text-green-200 mb-1">Tests Started</h4>
                  <p className="text-sm text-green-700 dark:text-green-300 mb-2">
                    Running tests from <code>e2e/</code> directory in the background.
                  </p>
                  <p className="text-xs text-green-600 dark:text-green-400">
                    Cycle ID: <code className="bg-green-100 dark:bg-green-800 px-1 rounded">{cycleId}</code>
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Info message */}
          {!triggerSuccess && !error && (
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
              <p className="text-sm text-blue-900 dark:text-blue-200">
                This will run all Playwright tests in the project's <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">e2e/</code> directory.
              </p>
            </div>
          )}

          {/* Force option */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="force"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              disabled={triggerMutation.isPending}
              className="rounded"
            />
            <label htmlFor="force" className="text-sm text-gray-700 dark:text-gray-300">
              Skip prerequisite checks
            </label>
          </div>

          {/* Running indicator */}
          {triggerMutation.isPending && (
            <div className="bg-purple-50 dark:bg-purple-900/20 border border-purple-200 dark:border-purple-800 rounded-lg p-4">
              <div className="flex items-center gap-3">
                <Loader2 className="w-5 h-5 animate-spin text-purple-600" />
                <div>
                  <p className="font-medium text-purple-900 dark:text-purple-200">Starting Tests...</p>
                  <p className="text-sm text-purple-700 dark:text-purple-300">This may take a moment</p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 p-6 border-t dark:border-gray-700">
          <button
            onClick={handleClose}
            disabled={triggerMutation.isPending}
            className={`flex-1 px-4 py-2 border rounded transition-colors ${
              triggerMutation.isPending
                ? 'border-gray-200 dark:border-gray-700 text-gray-400 cursor-not-allowed'
                : 'border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
          >
            {triggerMutation.isPending ? 'Please Wait...' : 'Cancel'}
          </button>
          <button
            onClick={handleRunTests}
            disabled={triggerMutation.isPending || triggerSuccess}
            className={`flex-1 px-4 py-2 rounded flex items-center justify-center gap-2 transition-colors ${
              triggerMutation.isPending || triggerSuccess
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-purple-600 text-white hover:bg-purple-700'
            }`}
          >
            {triggerMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Starting...
              </>
            ) : triggerSuccess ? (
              <>
                <CheckCircle className="w-4 h-4" />
                Started
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Run Tests
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
