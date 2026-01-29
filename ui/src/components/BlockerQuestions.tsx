/**
 * Blocker Questions Component (Feature #9)
 *
 * Conversational interface for asking users about potential blockers
 * before UAT test execution. Presents detected blockers and collects
 * user preferences (wait/skip/mock) for each.
 *
 * This is a conversational UI that integrates with the AssistantPanel.
 */

import { useState } from 'react'
import { AlertCircle, Mail, MessageSquare, CreditCard, Globe, Database, Lock } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export type BlockerType =
  | 'email_verification'
  | 'sms'
  | 'payment_gateway'
  | 'external_api'
  | 'database_migration'
  | 'auth_provider'

export type BlockerAction = 'wait' | 'skip' | 'mock'

export interface BlockerConfig {
  blocker_type: BlockerType
  detected: boolean
  action?: BlockerAction
  reason: string
  affected_tests: string[]
  notes?: string
}

export interface DetectBlockersResponse {
  success: boolean
  project_name: string
  blockers_detected: BlockerConfig[]
  total_blockers: number
  critical_blockers: number
  message: string
  recommendations: string
}

// ============================================================================
// Props
// ============================================================================

interface BlockerQuestionsProps {
  projectName: string
  blockers: BlockerConfig[]
  onConfigure: (blockers: BlockerConfig[]) => void
  onSkip?: () => void
}

// ============================================================================
// Helpers
// ============================================================================

function getBlockerIcon(type: BlockerType) {
  const icons = {
    email_verification: Mail,
    sms: MessageSquare,
    payment_gateway: CreditCard,
    external_api: Globe,
    database_migration: Database,
    auth_provider: Lock,
  }
  return icons[type] || AlertCircle
}

function getBlockerLabel(type: BlockerType): string {
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function getActionDescription(action: BlockerAction): string {
  const descriptions = {
    wait: 'I will pause and wait for you to manually configure the service before running tests.',
    skip: 'I will skip tests that depend on this service and continue with other tests.',
    mock: 'I will use test doubles/mocks instead of the real service for testing.',
  }
  return descriptions[action]
}

// ============================================================================
// Component
// ============================================================================

export function BlockerQuestions({
  projectName: _projectName, // Prefix with underscore to indicate intentionally unused
  blockers,
  onConfigure,
  onSkip
}: BlockerQuestionsProps) {
  const [selectedActions, setSelectedActions] = useState<Record<string, BlockerAction>>({})
  const [currentIndex, setCurrentIndex] = useState(0)

  const currentBlocker = blockers[currentIndex]
  const isLast = currentIndex === blockers.length - 1
  const isFirst = currentIndex === 0

  const handleSelectAction = (action: BlockerAction) => {
    setSelectedActions(prev => ({
      ...prev,
      [currentBlocker.blocker_type]: action
    }))
  }

  const handleNext = () => {
    if (!selectedActions[currentBlocker.blocker_type]) {
      return // Must select an action first
    }

    if (isLast) {
      // Submit all blockers
      const configuredBlockers = blockers.map(b => ({
        ...b,
        action: selectedActions[b.blocker_type]
      }))
      onConfigure(configuredBlockers)
    } else {
      setCurrentIndex(prev => prev + 1)
    }
  }

  const handleBack = () => {
    if (!isFirst) {
      setCurrentIndex(prev => prev - 1)
    }
  }

  const selectedAction = selectedActions[currentBlocker.blocker_type]

  if (!currentBlocker) {
    return null
  }

  const BlockerIcon = getBlockerIcon(currentBlocker.blocker_type)

  return (
    <div className="flex flex-col gap-4 p-6">
      {/* Progress Indicator */}
      <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
        <span>Question</span>
        <span className="font-semibold">{currentIndex + 1}</span>
        <span>of</span>
        <span className="font-semibold">{blockers.length}</span>
      </div>

      {/* Progress Bar */}
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          className="bg-purple-500 h-2 rounded-full transition-all duration-300"
          style={{ width: `${((currentIndex + 1) / blockers.length) * 100}%` }}
        />
      </div>

      {/* Blocker Card */}
      <div className="border-2 border-purple-500 dark:border-purple-400 rounded-lg p-6 bg-white dark:bg-gray-800 shadow-lg">
        {/* Icon and Title */}
        <div className="flex items-start gap-4 mb-4">
          <div className="p-3 bg-purple-100 dark:bg-purple-900 rounded-lg">
            <BlockerIcon className="w-6 h-6 text-purple-600 dark:text-purple-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {getBlockerLabel(currentBlocker.blocker_type)} Detected
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              {currentBlocker.reason}
            </p>
          </div>
        </div>

        {/* Affected Tests */}
        {currentBlocker.affected_tests.length > 0 && (
          <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
            <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Affected Tests ({currentBlocker.affected_tests.length}):
            </p>
            <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
              {currentBlocker.affected_tests.map((test, idx) => (
                <li key={idx} className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-purple-500 rounded-full" />
                  {test}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Notes */}
        {currentBlocker.notes && (
          <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
            <p className="text-sm text-blue-800 dark:text-blue-300">
              💡 <strong>Tip:</strong> {currentBlocker.notes}
            </p>
          </div>
        )}

        {/* Question */}
        <div className="mb-4">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">
            How should I handle {getBlockerLabel(currentBlocker.blocker_type).toLowerCase()}?
          </p>

          {/* Action Options */}
          <div className="space-y-2">
            {(['wait', 'skip', 'mock'] as BlockerAction[]).map((action) => {
              const isSelected = selectedAction === action
              return (
                <button
                  key={action}
                  onClick={() => handleSelectAction(action)}
                  className={`
                    w-full text-left p-4 rounded-lg border-2 transition-all duration-200
                    ${isSelected
                      ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20'
                      : 'border-gray-300 dark:border-gray-600 hover:border-purple-300 dark:hover:border-purple-600'
                    }
                  `}
                >
                  <div className="flex items-start gap-3">
                    <div className={`
                      w-5 h-5 rounded-full border-2 flex items-center justify-center mt-0.5
                      ${isSelected
                        ? 'border-purple-500 bg-purple-500'
                        : 'border-gray-400 dark:border-gray-600'
                      }
                    `}>
                      {isSelected && (
                        <div className="w-2 h-2 bg-white rounded-full" />
                      )}
                    </div>
                    <div className="flex-1">
                      <p className="font-semibold text-gray-900 dark:text-gray-100 capitalize">
                        {action}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        {getActionDescription(action)}
                      </p>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Navigation Buttons */}
      <div className="flex justify-between gap-3">
        <button
          onClick={onSkip}
          className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
        >
          Skip Blocker Configuration
        </button>

        <div className="flex gap-3">
          {!isFirst && (
            <button
              onClick={handleBack}
              className="px-4 py-2 border-2 border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              Back
            </button>
          )}
          <button
            onClick={handleNext}
            disabled={!selectedAction}
            className={`
              px-6 py-2 rounded-lg font-semibold transition-all duration-200
              ${selectedAction
                ? 'bg-purple-500 text-white hover:bg-purple-600 cursor-pointer'
                : 'bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-500 cursor-not-allowed'
              }
            `}
          >
            {isLast ? 'Finish Configuration' : 'Next'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Hook for Blocker Detection
// ============================================================================

export function useBlockerDetection() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const detectBlockers = async (projectName: string): Promise<DetectBlockersResponse> => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch(`/api/uat/detect-blockers`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: projectName,
        }),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const data = await response.json()
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to detect blockers'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }

  const configureBlockers = async (projectName: string, blockers: BlockerConfig[]): Promise<void> => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch(`/api/uat/configure-blockers`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: projectName,
          blockers,
        }),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      await response.json()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to configure blockers'
      setError(message)
      throw err
    } finally {
      setIsLoading(false)
    }
  }

  return {
    detectBlockers,
    configureBlockers,
    isLoading,
    error,
  }
}
