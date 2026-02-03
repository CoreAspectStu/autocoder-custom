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
import { AlertCircle, Mail, MessageSquare, CreditCard, Globe, Database, Lock, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import { ConnectionTestSkeleton } from './SkeletonLoader'
import { testConnection } from '../lib/api'

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

export interface ConnectionTestResult {
  success: boolean
  message: string
  details?: Record<string, any>
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
  projectName,
  blockers,
  onConfigure,
}: BlockerQuestionsProps) {
  const [selectedActions, setSelectedActions] = useState<Record<string, BlockerAction>>({})
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null)

  const currentBlocker = blockers[currentIndex]
  const isLast = currentIndex === blockers.length - 1
  const isFirst = currentIndex === 0

  const handleSelectAction = async (action: BlockerAction) => {
    setSelectedActions(prev => ({
      ...prev,
      [currentBlocker.blocker_type]: action
    }))

    // If "wait" is selected, test the connection
    if (action === 'wait') {
      await testBlockerConnection()
    }
  }

  const testBlockerConnection = async () => {
    setIsTesting(true)
    setTestResult(null)

    try {
      const result = await testConnection({
        blocker_id: `${currentBlocker.blocker_type}_${currentBlocker.blocker_type}`,
        blocker_type: mapBlockerTypeToAPI(currentBlocker.blocker_type),
        service: currentBlocker.blocker_type,
        timeout: 10
      })

      setTestResult({
        success: result.success,
        message: result.message,
        details: result.details
      })
    } catch (error) {
      setTestResult({
        success: false,
        message: error instanceof Error ? error.message : 'Failed to test connection'
      })
    } finally {
      setIsTesting(false)
    }
  }

  // Map UI blocker types to API blocker types
  const mapBlockerTypeToAPI = (type: BlockerType): string => {
    const mapping: Record<BlockerType, string> = {
      email_verification: 'service_unavailable',
      sms: 'service_unavailable',
      payment_gateway: 'api_key',
      external_api: 'service_unavailable',
      database_migration: 'resource_missing',
      auth_provider: 'auth_provider'
    }
    return mapping[type] || 'service_unavailable'
  }

  const handleNext = () => {
    const selectedAction = selectedActions[currentBlocker.blocker_type]
    if (!selectedAction) {
      return // Must select an action first
    }

    // For "wait" action, require successful connection test
    if (selectedAction === 'wait' && (!testResult || !testResult.success)) {
      return // Must have successful connection test
    }

    if (isLast) {
      // Submit all blockers
      const configuredBlockers = blockers.map(b => ({
        ...b,
        action: selectedActions[b.blocker_type]
      }))
      onConfigure(configuredBlockers)
    } else {
      // Reset test result for next blocker
      setTestResult(null)
      setCurrentIndex(prev => prev + 1)
    }
  }

  const handleRetry = () => {
    testBlockerConnection()
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
                  disabled={isTesting}
                  className={`
                    w-full text-left p-4 rounded-lg border-2 transition-all duration-200
                    ${isSelected
                      ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20'
                      : 'border-gray-300 dark:border-gray-600 hover:border-purple-300 dark:hover:border-purple-600'
                    }
                    ${isTesting ? 'opacity-50 cursor-not-allowed' : ''}
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

        {/* Connection Test Result - shown when "wait" is selected */}
        {selectedAction === 'wait' && (
          <div className="mt-4">
            {isTesting ? (
              <ConnectionTestSkeleton service={getBlockerLabel(currentBlocker.blocker_type)} />
            ) : testResult ? (
              <div className={`p-4 rounded-lg border-2 ${
                testResult.success
                  ? 'bg-green-50 dark:bg-green-900/20 border-green-500 dark:border-green-400'
                  : 'bg-red-50 dark:bg-red-900/20 border-red-500 dark:border-red-400'
              }`}>
                <div className="flex items-start gap-3">
                  {testResult.success ? (
                    <CheckCircle className="w-6 h-6 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                  ) : (
                    <XCircle className="w-6 h-6 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1">
                    <p className={`font-semibold ${
                      testResult.success
                        ? 'text-green-900 dark:text-green-100'
                        : 'text-red-900 dark:text-red-100'
                    }`}>
                      {testResult.success ? 'Connection Successful!' : 'Connection Failed'}
                    </p>
                    <p className={`text-sm mt-1 ${
                      testResult.success
                        ? 'text-green-700 dark:text-green-300'
                        : 'text-red-700 dark:text-red-300'
                    }`}>
                      {testResult.message}
                    </p>
                    {!testResult.success && (
                      <button
                        onClick={handleRetry}
                        className="mt-3 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                      >
                        <RefreshCw className="w-4 h-4" />
                        Retry Connection
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* Navigation Buttons */}
      <div className="flex justify-end gap-3">
        <div className="flex gap-3">
          {!isFirst && (
            <button
              onClick={handleBack}
              disabled={isTesting}
              className={`px-4 py-2 border-2 rounded-lg transition-colors ${
                isTesting
                  ? 'border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-600 cursor-not-allowed'
                  : 'border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              Back
            </button>
          )}
          <button
            onClick={handleNext}
            disabled={
              !selectedAction ||
              isTesting ||
              (selectedAction === 'wait' && (!testResult || !testResult.success))
            }
            className={`
              px-6 py-2 rounded-lg font-semibold transition-all duration-200
              ${selectedAction &&
                (selectedAction !== 'wait' || (testResult && testResult.success)) &&
                !isTesting
                ? 'bg-purple-500 text-white hover:bg-purple-600 cursor-pointer'
                : 'bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-500 cursor-not-allowed'
              }
            `}
          >
            {isTesting ? 'Testing Connection...' : isLast ? 'Finish Configuration' : 'Next'}
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
      // Get project path from registry
      const projectsResp = await fetch('/api/projects')
      const projects = await projectsResp.json()
      const project = projects.find((p: any) => p.name === projectName)

      if (!project) {
        throw new Error(`Project ${projectName} not found`)
      }

      // Use the new blocker detection API
      const response = await fetch('/api/blocker/detect', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          project_name: projectName,
          project_path: project.path,
        }),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const data = await response.json()

      // Transform the response to match the expected format
      const blockers: BlockerConfig[] = data.blockers.map((b: any) => ({
        blocker_type: b.blocker_type as BlockerType,
        detected: true,
        reason: b.description,
        affected_tests: b.affected_tests,
        notes: b.priority === 'critical' ? 'This is critical for test execution' : undefined,
      }))

      return {
        success: data.blockers_detected,
        project_name: projectName,
        blockers_detected: blockers,
        total_blockers: blockers.length,
        critical_blockers: blockers.filter((b: BlockerConfig) => b.notes?.includes('critical')).length,
        message: data.summary,
        recommendations: data.summary,
      }
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
      // Use the new blocker respond API for each configured blocker
      for (const blocker of blockers) {
        if (blocker.action) {
          const response = await fetch('/api/blocker/respond', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              blocker_id: `${blocker.blocker_type}_${blocker.blocker_type}`,
              action: blocker.action,
              project_name: projectName,
            }),
          })

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`)
          }
        }
      }
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
