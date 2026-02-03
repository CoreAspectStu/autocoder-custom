/**
 * Blocker Resolution Modal
 *
 * Conversational UI for resolving blockers before UAT test execution.
 * Presents one blocker at a time with clear action options.
 */

import { useState, useEffect } from 'react'
import { X, ChevronRight, ChevronLeft, Check, AlertTriangle, SkipForward, Key, Settings, Lock } from 'lucide-react'
import { useBlockerDetection, type Blocker } from '../../hooks/useBlockerDetection'

interface BlockerModalProps {
  projectName: string | null
  open: boolean
  onClose: () => void
  onComplete?: () => void
}

export function BlockerModal({ projectName, open, onClose, onComplete }: BlockerModalProps) {
  const {
    blockers,
    isDetecting,
    currentIndex,
    currentBlocker,
    detectBlockers,
    respondToBlocker,
    skipAll,
    setCurrentIndex,
    hasBlockers,
    isComplete
  } = useBlockerDetection(projectName)

  const [isProcessing, setIsProcessing] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set())

  // Auto-detect blockers when modal opens
  useEffect(() => {
    if (open && projectName && blockers.length === 0) {
      detectBlockers()
    }
  }, [open, projectName, blockers.length, detectBlockers])

  const handleSubmit = async (action: string, value?: string) => {
    setIsProcessing(true)
    try {
      await respondToBlocker({
        blocker_id: currentBlocker!.id,
        action: action as any,
        value
      })

      setCompletedIds(prev => new Set([...prev, currentBlocker!.id]))
      setInputValue('')

      // Check if complete
      if (isComplete) {
        onComplete?.()
        onClose()
      }
    } catch (error) {
      console.error('[BlockerModal] Failed to resolve blocker:', error)
    } finally {
      setIsProcessing(false)
    }
  }

  const handleSkipAll = async () => {
    setIsProcessing(true)
    try {
      await skipAll()
      onComplete?.()
      onClose()
    } catch (error) {
      console.error('[BlockerModal] Failed to skip all:', error)
    } finally {
      setIsProcessing(false)
    }
  }

  if (!open || !projectName) return null
  if (isDetecting) return <LoadingState />

  if (!hasBlockers) {
    return <NoBlockersState onClose={onClose} />
  }

  if (isComplete) {
    return <CompletionState onClose={onClose} total={blockers.length} />
  }

  const blocker = currentBlocker!

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b dark:border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Configuration Required</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Resolve blockers to continue with UAT testing
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress */}
        <div className="px-6 py-3 bg-gray-50 dark:bg-gray-900 border-b dark:border-gray-700">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-700 dark:text-gray-300">
              {currentIndex + 1} of {blockers.length} blockers
            </span>
            <div className="flex items-center gap-2">
              <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-purple-500 transition-all"
                  style={{ width: `${((currentIndex + 1) / blockers.length) * 100}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="mb-6">
            <div className="flex items-start gap-3 mb-4">
              <div className={`p-2 rounded-lg ${getBlockIconColor(blocker.blocker_type)}`}>
                {getBlockIcon(blocker.blocker_type)}
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-lg text-gray-900 dark:text-white">
                  {blocker.service.charAt(0).toUpperCase() + blocker.service.slice(1)} - {blocker.key_name || 'Configuration'}
                </h3>
                <p className="text-gray-600 dark:text-gray-400 mt-1">
                  {blocker.description}
                </p>
              </div>
              <div className={`px-2 py-1 rounded text-xs font-semibold ${getPriorityColor(blocker.priority)}`}>
                {blocker.priority.toUpperCase()}
              </div>
            </div>

            {blocker.affected_tests.length > 0 && (
              <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded">
                <p className="text-sm text-yellow-800 dark:text-yellow-200">
                  <strong>Affects:</strong> {blocker.affected_tests.join(', ')}
                </p>
              </div>
            )}
          </div>

          {/* Response Options */}
          <div className="space-y-3">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">What would you like to do?</p>

            {blocker.suggested_actions.includes('provide_key') && (
              <ApiKeyOption
                blocker={blocker}
                inputValue={inputValue}
                setInputValue={setInputValue}
                onSubmit={(value) => handleSubmit('provide_key', value)}
                isProcessing={isProcessing}
              />
            )}

            {blocker.suggested_actions.includes('skip') && (
              <button
                onClick={() => handleSubmit('skip')}
                disabled={isProcessing}
                className="w-full flex items-center gap-3 p-4 border-2 border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
              >
                <div className="p-2 bg-blue-100 dark:bg-blue-900 rounded">
                  <SkipForward className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                </div>
                <div className="text-left">
                  <div className="font-medium text-gray-900 dark:text-white">Skip this test</div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">Tests requiring this service will be skipped</div>
                </div>
              </button>
            )}

            {blocker.suggested_actions.includes('mock') && (
              <button
                onClick={() => handleSubmit('mock')}
                disabled={isProcessing}
                className="w-full flex items-center gap-3 p-4 border-2 border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
              >
                <div className="p-2 bg-purple-100 dark:bg-purple-900 rounded">
                  <Settings className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                </div>
                <div className="text-left">
                  <div className="font-medium text-gray-900 dark:text-white">Use mock service</div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">Tests will use mock data instead</div>
                </div>
              </button>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t dark:border-gray-700">
          <button
            onClick={handleSkipAll}
            disabled={isProcessing}
            className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 disabled:opacity-50"
          >
            Skip all remaining blockers
          </button>

          {currentIndex > 0 && (
            <button
              onClick={() => setCurrentIndex((prev: number) => prev - 1)}
              disabled={isProcessing}
              className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 disabled:opacity-50"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </button>
          )}

          {currentIndex < blockers.length - 1 && (
            <button
              onClick={() => setCurrentIndex((prev: number) => prev + 1)}
              disabled={isProcessing}
              className="flex items-center gap-1 px-3 py-2 text-sm bg-purple-500 text-white rounded hover:bg-purple-600 disabled:opacity-50"
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-8 shadow-2xl">
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-700 dark:text-gray-300">Detecting blockers...</p>
        </div>
      </div>
    </div>
  )
}

function NoBlockersState({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl w-full max-w-md p-8 text-center">
        <div className="flex justify-center mb-4">
          <Check className="w-12 h-12 text-green-500" />
        </div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">No Blockers Detected</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-6">
          All required services and configuration are available. You can proceed with UAT testing.
        </p>
        <button
          onClick={onClose}
          className="px-6 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600"
        >
          Continue to Testing
        </button>
      </div>
    </div>
  )
}

function CompletionState({ onClose, total }: { onClose: () => void; total: number }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-2xl w-full max-w-md p-8 text-center">
        <div className="flex justify-center mb-4">
          <Check className="w-12 h-12 text-green-500" />
        </div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Blockers Resolved!</h2>
        <p className="text-gray-600 dark:text-gray-400 mb-6">
          All {total} blockers have been addressed. You can now run UAT tests.
        </p>
        <button
          onClick={onClose}
          className="px-6 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600"
        >
          Continue to Testing
        </button>
      </div>
    </div>
  )
}

function ApiKeyOption({
  blocker,
  inputValue,
  setInputValue,
  onSubmit,
  isProcessing
}: {
  blocker: Blocker
  inputValue: string
  setInputValue: (value: string) => void
  onSubmit: (value: string) => void
  isProcessing: boolean
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Key className="w-4 h-4 text-gray-500" />
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Provide {blocker.key_name}:
        </label>
      </div>
      <input
        type="password"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        placeholder={`Enter ${blocker.key_name}...`}
        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-purple-500"
      />
      <button
        onClick={() => onSubmit(inputValue)}
        disabled={isProcessing || !inputValue}
        className="w-full px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {isProcessing ? (
          <>
            <div className="w-4 h-4 border-2 border-white/30 rounded-full animate-spin" />
            Saving...
          </>
        ) : (
          <>
            <Check className="w-4 h-4" />
            Save & Continue
          </>
        )}
      </button>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        <Lock className="w-3 h-3 inline" /> Encrypted and stored securely
      </p>
    </div>
  )
}

// Helper functions
function getBlockIcon(type: string) {
  const icons: Record<string, React.ReactNode> = {
    api_key: <Key className="w-5 h-5" />,
    config_decision: <Settings className="w-5 h-5" />,
    resource_missing: <AlertTriangle className="w-5 h-5" />,
    service_unavailable: <AlertTriangle className="w-5 h-5" />
  }
  return icons[type] || <Settings className="w-5 h-5" />
}

function getBlockIconColor(type: string) {
  const colors: Record<string, string> = {
    api_key: 'bg-red-100 text-red-600 dark:bg-red-900 dark:text-red-400',
    config_decision: 'bg-blue-100 text-blue-600 dark:bg-blue-900 dark:text-blue-400',
    resource_missing: 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900 dark:text-yellow-400',
    service_unavailable: 'bg-orange-100 text-orange-600 dark:bg-orange-900 dark:text-orange-400'
  }
  return colors[type] || 'bg-gray-100 text-gray-600'
}

function getPriorityColor(priority: string) {
  const colors: Record<string, string> = {
    critical: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
    high: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
    medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
    low: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300'
  }
  return colors[priority] || 'bg-gray-100 text-gray-700'
}
