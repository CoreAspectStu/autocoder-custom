/**
 * UAT Card Component
 *
 * Displays UAT test results on the Kanban board with:
 * - Test status (passed, failed, running)
 * - Test details (type, duration, score)
 * - Visual diff thumbnails for visual tests
 * - Accessibility violations for a11y tests
 * - Link to full test reports
 */

import { useState } from 'react'
import {
  CheckCircle,
  XCircle,
  Loader2,
  Eye,
  AlertTriangle,
  Clock,
  FileText,
  ChevronDown,
  ChevronUp
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export type UATTestType = 'visual' | 'a11y' | 'api' | 'comprehensive'

export type UATTestStatus = 'passed' | 'failed' | 'running' | 'pending'

export interface UATTestResult {
  test_id: string
  test_name: string
  test_type: UATTestType
  status: UATTestStatus
  score?: number
  duration_seconds?: number
  started_at?: string
  completed_at?: string

  // Visual test specific
  visual_diff?: {
    baseline_path?: string
    current_path?: string
    diff_path?: string
    diff_percentage?: number
    thumbnail?: string
  }

  // A11y test specific
  a11y_violations?: {
    total: number
    critical: number
    serious: number
    moderate: number
    minor: number
  }

  // API test specific
  api_results?: {
    endpoints_tested: number
    passed: number
    failed: number
    avg_response_time_ms: number
  }

  // Comprehensive test results
  tool_results?: {
    tool: string
    passed: boolean
    score?: number
    total_tests: number
    passed_tests: number
    failed_tests: number
  }[]

  report_path?: string
  error?: string
}

interface UATCardProps {
  result: UATTestResult
  onClick?: () => void
  compact?: boolean
}

// ============================================================================
// Helpers
// ============================================================================

function getTestTypeIcon(type: UATTestType) {
  const icons = {
    visual: Eye,
    a11y: AlertTriangle,
    api: FileText,
    comprehensive: CheckCircle
  }
  return icons[type] || FileText
}

function getTestTypeLabel(type: UATTestType): string {
  const labels = {
    visual: 'Visual Regression',
    a11y: 'Accessibility',
    api: 'API Testing',
    comprehensive: 'Comprehensive UAT'
  }
  return labels[type] || type
}

function getTestTypeColor(type: UATTestType): string {
  const colors = {
    visual: 'text-purple-600 dark:text-purple-400',
    a11y: 'text-blue-600 dark:text-blue-400',
    api: 'text-green-600 dark:text-green-400',
    comprehensive: 'text-orange-600 dark:text-orange-400'
  }
  return colors[type] || 'text-gray-600'
}

function getTestTypeBgColor(type: UATTestType): string {
  const colors = {
    visual: 'bg-purple-100 dark:bg-purple-900/30',
    a11y: 'bg-blue-100 dark:bg-blue-900/30',
    api: 'bg-green-100 dark:bg-green-900/30',
    comprehensive: 'bg-orange-100 dark:bg-orange-900/30'
  }
  return colors[type] || 'bg-gray-100 dark:bg-gray-800'
}

function getStatusIcon(status: UATTestStatus) {
  switch (status) {
    case 'passed':
      return CheckCircle
    case 'failed':
      return XCircle
    case 'running':
      return Loader2
    case 'pending':
      return Clock
    default:
      return Clock
  }
}

function getStatusColor(status: UATTestStatus): string {
  const colors = {
    passed: 'text-green-600 dark:text-green-400',
    failed: 'text-red-600 dark:text-red-400',
    running: 'text-blue-600 dark:text-blue-400',
    pending: 'text-gray-600 dark:text-gray-400'
  }
  return colors[status] || 'text-gray-600'
}

function getStatusBgColor(status: UATTestStatus): string {
  const colors = {
    passed: 'bg-green-100 dark:bg-green-900/30',
    failed: 'bg-red-100 dark:bg-red-900/30',
    running: 'bg-blue-100 dark:bg-blue-900/30',
    pending: 'bg-gray-100 dark:bg-gray-800'
  }
  return colors[status] || 'bg-gray-100'
}

function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`
  }
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
}

// ============================================================================
// Components
// ============================================================================

export function UATCard({ result, onClick, compact = false }: UATCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const TestTypeIcon = getTestTypeIcon(result.test_type)
  const StatusIcon = getStatusIcon(result.status)

  const isRunning = result.status === 'running'

  return (
    <div
      onClick={onClick}
      className={`
        border-2 rounded-lg p-4 transition-all duration-200 cursor-pointer
        ${result.status === 'passed'
          ? 'border-green-300 dark:border-green-700 hover:border-green-500 dark:hover:border-green-500'
          : result.status === 'failed'
          ? 'border-red-300 dark:border-red-700 hover:border-red-500 dark:hover:border-red-500'
          : 'border-blue-300 dark:border-blue-700 hover:border-blue-500 dark:hover:border-blue-500'
        }
      `}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        {/* Status Icon */}
        <div className={`p-2 rounded-lg ${getStatusBgColor(result.status)}`}>
          <StatusIcon className={`w-5 h-5 ${getStatusColor(result.status)} ${isRunning ? 'animate-spin' : ''}`} />
        </div>

        {/* Test Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs font-semibold px-2 py-0.5 rounded ${getTestTypeBgColor(result.test_type)} ${getTestTypeColor(result.test_type)}`}>
              {getTestTypeLabel(result.test_type)}
            </span>
            {result.score !== undefined && (
              <span className={`text-sm font-bold ${result.score >= 90 ? 'text-green-600 dark:text-green-400' : result.score >= 70 ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-600 dark:text-red-400'}`}>
                {result.score}% Score
              </span>
            )}
          </div>

          <h4 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
            {result.test_name}
          </h4>

          {/* Metadata */}
          <div className="flex items-center gap-3 mt-2 text-sm text-gray-600 dark:text-gray-400">
            {result.duration_seconds && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatDuration(result.duration_seconds)}
              </span>
            )}
            {result.completed_at && (
              <span>
                {new Date(result.completed_at).toLocaleString()}
              </span>
            )}
          </div>
        </div>

        {/* Expand/Collapse Button */}
        {(result.visual_diff || result.a11y_violations || result.api_results || result.tool_results) && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              setIsExpanded(!isExpanded)
            }}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
          >
            {isExpanded ? (
              <ChevronUp className="w-4 h-4 text-gray-600" />
            ) : (
              <ChevronDown className="w-4 h-4 text-gray-600" />
            )}
          </button>
        )}
      </div>

      {/* Expanded Details */}
      {isExpanded && !compact && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 space-y-3">
          {/* Visual Diff */}
          {result.visual_diff && (
            <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
              <p className="text-sm font-medium text-purple-900 dark:text-purple-100 mb-2">
                Visual Regression Results
              </p>
              {result.visual_diff.thumbnail && (
                <div className="mb-2">
                  <img
                    src={result.visual_diff.thumbnail}
                    alt="Visual diff"
                    className="w-full rounded border border-gray-300 dark:border-gray-600"
                  />
                </div>
              )}
              {result.visual_diff.diff_percentage !== undefined && (
                <p className="text-sm text-purple-700 dark:text-purple-300">
                  Difference: {result.visual_diff.diff_percentage.toFixed(1)}%
                </p>
              )}
            </div>
          )}

          {/* A11y Violations */}
          {result.a11y_violations && (
            <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
              <p className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">
                Accessibility Violations
              </p>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <span className="text-red-600 dark:text-red-400">
                  Critical: {result.a11y_violations.critical}
                </span>
                <span className="text-orange-600 dark:text-orange-400">
                  Serious: {result.a11y_violations.serious}
                </span>
                <span className="text-yellow-600 dark:text-yellow-400">
                  Moderate: {result.a11y_violations.moderate}
                </span>
                <span className="text-gray-600 dark:text-gray-400">
                  Minor: {result.a11y_violations.minor}
                </span>
              </div>
              <p className="text-sm text-blue-700 dark:text-blue-300 mt-2">
                Total: {result.a11y_violations.total} violations
              </p>
            </div>
          )}

          {/* API Results */}
          {result.api_results && (
            <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
              <p className="text-sm font-medium text-green-900 dark:text-green-100 mb-2">
                API Test Results
              </p>
              <div className="space-y-1 text-sm">
                <p className="text-green-700 dark:text-green-300">
                  Endpoints tested: {result.api_results.endpoints_tested}
                </p>
                <p className="text-green-700 dark:text-green-300">
                  Passed: {result.api_results.passed} / Failed: {result.api_results.failed}
                </p>
                <p className="text-green-700 dark:text-green-300">
                  Avg response: {result.api_results.avg_response_time_ms}ms
                </p>
              </div>
            </div>
          )}

          {/* Tool Results (Comprehensive) */}
          {result.tool_results && (
            <div className="p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg">
              <p className="text-sm font-medium text-orange-900 dark:text-orange-100 mb-2">
                Tool Results
              </p>
              <div className="space-y-2">
                {result.tool_results.map((tool, idx) => (
                  <div key={idx} className="flex items-center justify-between text-sm">
                    <span className="capitalize text-gray-700 dark:text-gray-300">
                      {tool.tool}
                    </span>
                    <span className={tool.passed ? 'text-green-600' : 'text-red-600'}>
                      {tool.passed ? 'Passed' : 'Failed'}
                      {tool.score !== undefined && ` (${tool.score}%)`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error Message */}
          {result.error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
              <p className="text-sm text-red-700 dark:text-red-300">
                {result.error}
              </p>
            </div>
          )}

          {/* Report Link */}
          {result.report_path && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                // Navigate to report
                console.log('Navigate to report:', result.report_path)
              }}
              className="text-sm text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-300"
            >
              View Full Report →
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Compact Card Variant (for list views)
// ============================================================================

export function UATCardCompact({ result, onClick }: UATCardProps) {
  const StatusIcon = getStatusIcon(result.status)

  return (
    <div
      onClick={onClick}
      className={`
        flex items-center gap-3 p-3 rounded-lg border-2 transition-all duration-200 cursor-pointer hover:shadow-md
        ${result.status === 'passed'
          ? 'border-green-300 dark:border-green-700'
          : result.status === 'failed'
          ? 'border-red-300 dark:border-red-700'
          : 'border-blue-300 dark:border-blue-700'
        }
      `}
    >
      <StatusIcon className={`w-4 h-4 ${getStatusColor(result.status)} ${result.status === 'running' ? 'animate-spin' : ''}`} />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
          {result.test_name}
        </p>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {getTestTypeLabel(result.test_type)}
        </p>
      </div>

      {result.score !== undefined && (
        <span className={`text-sm font-bold ${result.score >= 90 ? 'text-green-600 dark:text-green-400' : result.score >= 70 ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-600 dark:text-red-400'}`}>
          {result.score}%
        </span>
      )}
    </div>
  )
}

// ============================================================================
// Card Grid (for displaying multiple cards)
// ============================================================================

interface UATCardGridProps {
  results: UATTestResult[]
  onCardClick?: (result: UATTestResult) => void
  compact?: boolean
}

export function UATCardGrid({ results, onCardClick, compact = false }: UATCardGridProps) {
  if (results.length === 0) {
    return (
      <div className="text-center py-12">
        <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
        <p className="text-gray-600 dark:text-gray-400">No UAT test results available</p>
      </div>
    )
  }

  return (
    <div className={`grid gap-4 ${compact ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'}`}>
      {results.map((result) => (
        <UATCard
          key={result.test_id}
          result={result}
          onClick={() => onCardClick?.(result)}
          compact={compact}
        />
      ))}
    </div>
  )
}

// ============================================================================
// Summary Stats (for dashboard view)
// ============================================================================

interface UATSummaryStatsProps {
  results: UATTestResult[]
}

export function UATSummaryStats({ results }: UATSummaryStatsProps) {
  const total = results.length
  const passed = results.filter(r => r.status === 'passed').length
  const failed = results.filter(r => r.status === 'failed').length
  const running = results.filter(r => r.status === 'running').length
  const pending = results.filter(r => r.status === 'pending').length

  const avgScore = results
    .filter(r => r.score !== undefined)
    .reduce((sum, r) => sum + (r.score || 0), 0) / Math.max(results.filter(r => r.score !== undefined).length, 1)

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg text-center">
        <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{total}</p>
        <p className="text-sm text-gray-600 dark:text-gray-400">Total Tests</p>
      </div>

      <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg text-center">
        <p className="text-2xl font-bold text-green-600 dark:text-green-400">{passed}</p>
        <p className="text-sm text-green-700 dark:text-green-300">Passed</p>
      </div>

      <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg text-center">
        <p className="text-2xl font-bold text-red-600 dark:text-red-400">{failed}</p>
        <p className="text-sm text-red-700 dark:text-red-300">Failed</p>
      </div>

      <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-center">
        <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{running}</p>
        <p className="text-sm text-blue-700 dark:text-blue-300">Running</p>
      </div>

      <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg text-center">
        <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
          {avgScore > 0 ? avgScore.toFixed(0) : '-'}
        </p>
        <p className="text-sm text-purple-700 dark:text-purple-300">Avg Score</p>
      </div>
    </div>
  )
}

export default UATCard
