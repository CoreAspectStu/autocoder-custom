/**
 * Progress Tracker Component
 *
 * Displays UAT test execution progress with:
 * - Overall aggregate statistics (total journeys, pass rate, execution stage)
 * - Per-journey progress cards with navigation
 * - Failures summary grouped by category and severity
 * - Real-time updates via WebSocket
 *
 * Features:
 * - Clickable navigation to journey details and results
 * - Failure categorization with emoji icons
 * - Severity-based visual highlighting
 * - Export capabilities (Markdown, HTML)
 * - Estimated time remaining calculation
 */

import { useState, useMemo } from 'react'
import {
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  TrendingUp,
  ChevronDown,
  ChevronRight,
  Download,
  RefreshCw,
  Link as LinkIcon
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export type ExecutionStage =
  | 'not_started'
  | 'parsing'
  | 'extraction'
  | 'generation'
  | 'execution'
  | 'processing'
  | 'updating'
  | 'complete'
  | 'failed'

export type JourneyStatus = 'passed' | 'failed' | 'pending'

export type FailureCategory =
  | 'selector'
  | 'timeout'
  | 'assertion'
  | 'network'
  | 'visual'
  | 'a11y'
  | 'performance'
  | 'critical'

export type SeverityLevel = 'critical' | 'high' | 'medium' | 'low'

export interface FailureInfo {
  id: string
  journey_id: string
  scenario: string
  category: FailureCategory
  severity: SeverityLevel
  message: string
  selector?: string
  element?: string
  url?: string
  screenshot?: string
  timestamp: string
}

export interface FailureGroup {
  category: FailureCategory
  icon: string
  label: string
  failures: FailureInfo[]
  count: number
  bySeverity: Record<SeverityLevel, number>
}

export interface JourneyStats {
  journey_id: string
  journey_name: string
  total_scenarios: number
  completed_scenarios: number
  passed_scenarios: number
  failed_scenarios: number
  pass_rate: number
  status: JourneyStatus
  execution_stage: ExecutionStage
  started_at?: string
  completed_at?: string
  details_url?: string
  results_url?: string
  failures_url?: string
}

export interface OverallStats {
  total_journeys: number
  total_scenarios: number
  completed_scenarios: number
  passed_scenarios: number
  failed_scenarios: number
  pass_rate: number
  execution_stage: ExecutionStage
  stage_history: { stage: ExecutionStage; timestamp: string }[]
  started_at?: string
  estimated_completion?: string
}

export interface ProgressTrackerProps {
  overallStats: OverallStats
  journeyStats: JourneyStats[]
  failures: FailureInfo[]
  onJourneyClick?: (journeyId: string) => void
  onResultsClick?: (journeyId: string) => void
  onFailuresClick?: (journeyId: string) => void
  onRefresh?: () => void
  isRefreshing?: boolean
}

// ============================================================================
// Helpers
// ============================================================================

function getStageLabel(stage: ExecutionStage): string {
  const labels: Record<ExecutionStage, string> = {
    not_started: 'Not Started',
    parsing: 'Parsing Specification',
    extraction: 'Extracting Scenarios',
    generation: 'Generating Tests',
    execution: 'Running Tests',
    processing: 'Processing Results',
    updating: 'Updating Database',
    complete: 'Complete',
    failed: 'Failed'
  }
  return labels[stage]
}

function getStageColor(stage: ExecutionStage): string {
  const colors: Record<ExecutionStage, string> = {
    not_started: 'text-gray-500',
    parsing: 'text-blue-500',
    extraction: 'text-indigo-500',
    generation: 'text-purple-500',
    execution: 'text-yellow-500',
    processing: 'text-orange-500',
    updating: 'text-cyan-500',
    complete: 'text-green-500',
    failed: 'text-red-500'
  }
  return colors[stage]
}

function getStageBgColor(stage: ExecutionStage): string {
  const colors: Record<ExecutionStage, string> = {
    not_started: 'bg-gray-100 dark:bg-gray-800',
    parsing: 'bg-blue-100 dark:bg-blue-900/30',
    extraction: 'bg-indigo-100 dark:bg-indigo-900/30',
    generation: 'bg-purple-100 dark:bg-purple-900/30',
    execution: 'bg-yellow-100 dark:bg-yellow-900/30',
    processing: 'bg-orange-100 dark:bg-orange-900/30',
    updating: 'bg-cyan-100 dark:bg-cyan-900/30',
    complete: 'bg-green-100 dark:bg-green-900/30',
    failed: 'bg-red-100 dark:bg-red-900/30'
  }
  return colors[stage]
}

function getStatusColor(status: JourneyStatus): string {
  const colors: Record<JourneyStatus, string> = {
    passed: 'text-green-600 dark:text-green-400',
    failed: 'text-red-600 dark:text-red-400',
    pending: 'text-gray-600 dark:text-gray-400'
  }
  return colors[status]
}

function getStatusBgColor(status: JourneyStatus): string {
  const colors: Record<JourneyStatus, string> = {
    passed: 'bg-green-100 dark:bg-green-900/30',
    failed: 'bg-red-100 dark:bg-red-900/30',
    pending: 'bg-gray-100 dark:bg-gray-800'
  }
  return colors[status]
}

function getCategoryIcon(category: FailureCategory): string {
  const icons: Record<FailureCategory, string> = {
    selector: '🔍',
    timeout: '⏱️',
    assertion: '❌',
    network: '🌐',
    visual: '🎨',
    a11y: '♿',
    performance: '📊',
    critical: '🚨'
  }
  return icons[category]
}

function getCategoryLabel(category: FailureCategory): string {
  const labels: Record<FailureCategory, string> = {
    selector: 'Selector Issues',
    timeout: 'Timeouts',
    assertion: 'Assertion Failures',
    network: 'Network Errors',
    visual: 'Visual Regressions',
    a11y: 'Accessibility Violations',
    performance: 'Performance Issues',
    critical: 'Critical Failures'
  }
  return labels[category]
}

function getSeverityColor(severity: SeverityLevel): string {
  const colors: Record<SeverityLevel, string> = {
    critical: 'text-red-700 dark:text-red-300 font-bold',
    high: 'text-orange-600 dark:text-orange-400',
    medium: 'text-yellow-600 dark:text-yellow-400',
    low: 'text-gray-600 dark:text-gray-400'
  }
  return colors[severity]
}

function groupFailuresByCategory(failures: FailureInfo[]): FailureGroup[] {
  const groups: Record<FailureCategory, FailureInfo[]> = {
    selector: [],
    timeout: [],
    assertion: [],
    network: [],
    visual: [],
    a11y: [],
    performance: [],
    critical: []
  }

  failures.forEach(failure => {
    groups[failure.category].push(failure)
  })

  return Object.entries(groups)
    .filter(([_, failures]) => failures.length > 0)
    .map(([category, failures]) => {
      const bySeverity: Record<SeverityLevel, number> = {
        critical: 0,
        high: 0,
        medium: 0,
        low: 0
      }
      failures.forEach(f => bySeverity[f.severity]++)

      return {
        category: category as FailureCategory,
        icon: getCategoryIcon(category as FailureCategory),
        label: getCategoryLabel(category as FailureCategory),
        failures,
        count: failures.length,
        bySeverity
      }
    })
    .sort((a, b) => b.count - a.count)
}

function formatTimeRemaining(seconds?: number): string {
  if (!seconds) return 'Calculating...'
  if (seconds < 60) return `${seconds}s remaining`
  const minutes = Math.ceil(seconds / 60)
  if (minutes < 60) return `${minutes}m remaining`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m remaining` : `${hours}h remaining`
}

// ============================================================================
// Components
// ============================================================================

export function ProgressTracker({
  overallStats,
  journeyStats,
  failures,
  onJourneyClick,
  onResultsClick,
  onFailuresClick,
  onRefresh,
  isRefreshing = false
}: ProgressTrackerProps) {
  const [expandedJourney, setExpandedJourney] = useState<string | null>(null)
  const [expandedFailureGroup, setExpandedFailureGroup] = useState<Set<FailureCategory>>(new Set())

  // Calculate estimated time remaining
  const timeRemaining = useMemo(() => {
    if (!overallStats.started_at || overallStats.execution_stage === 'complete') {
      return undefined
    }

    const elapsed = (Date.now() - new Date(overallStats.started_at).getTime()) / 1000
    const progress = overallStats.completed_scenarios / Math.max(overallStats.total_scenarios, 1)
    if (progress <= 0) return undefined

    const totalEstimated = elapsed / progress
    return Math.max(0, totalEstimated - elapsed)
  }, [overallStats])

  // Group failures by category
  const failureGroups = useMemo(() => groupFailuresByCategory(failures), [failures])

  const toggleFailureGroup = (category: FailureCategory) => {
    setExpandedFailureGroup(prev => {
      const newSet = new Set(prev)
      if (newSet.has(category)) {
        newSet.delete(category)
      } else {
        newSet.add(category)
      }
      return newSet
    })
  }

  const exportToMarkdown = () => {
    let markdown = `# UAT Test Progress Report\n\n`
    markdown += `## Overall Statistics\n\n`
    markdown += `- **Total Journeys**: ${overallStats.total_journeys}\n`
    markdown += `- **Total Scenarios**: ${overallStats.total_scenarios}\n`
    markdown += `- **Completed**: ${overallStats.completed_scenarios}\n`
    markdown += `- **Passed**: ${overallStats.passed_scenarios}\n`
    markdown += `- **Failed**: ${overallStats.failed_scenarios}\n`
    markdown += `- **Pass Rate**: ${overallStats.pass_rate.toFixed(1)}%\n`
    markdown += `- **Stage**: ${getStageLabel(overallStats.execution_stage)}\n\n`

    if (failureGroups.length > 0) {
      markdown += `## Failures Summary\n\n`
      failureGroups.forEach(group => {
        markdown += `### ${group.icon} ${group.label} (${group.count})\n\n`
        group.failures.forEach(f => {
          markdown += `- **${f.scenario}** (${f.severity}): ${f.message}\n`
        })
        markdown += '\n'
      })
    }

    return markdown
  }

  return (
    <div className="space-y-6">
      {/* Header with Refresh */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
          UAT Test Progress
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigator.clipboard.writeText(exportToMarkdown())}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
            title="Copy Markdown summary"
          >
            <Download className="w-4 h-4 text-gray-600 dark:text-gray-400" />
          </button>
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className={`p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors ${
              isRefreshing ? 'animate-spin' : ''
            }`}
            title="Refresh progress"
          >
            <RefreshCw className="w-4 h-4 text-gray-600 dark:text-gray-400" />
          </button>
        </div>
      </div>

      {/* Overall Stats Card */}
      <OverallStatsCard stats={overallStats} timeRemaining={timeRemaining} />

      {/* Execution Stage Indicator */}
      <StageIndicator stage={overallStats.execution_stage} history={overallStats.stage_history} />

      {/* Journey Progress Cards */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Journey Progress
        </h3>
        <div className="grid gap-4">
          {journeyStats.map(journey => (
            <JourneyProgressCard
              key={journey.journey_id}
              journey={journey}
              isExpanded={expandedJourney === journey.journey_id}
              onClick={() => onJourneyClick?.(journey.journey_id)}
              onToggleExpand={() => setExpandedJourney(
                expandedJourney === journey.journey_id ? null : journey.journey_id
              )}
              onResultsClick={() => onResultsClick?.(journey.journey_id)}
              onFailuresClick={() => onFailuresClick?.(journey.journey_id)}
            />
          ))}
        </div>
      </div>

      {/* Failures Summary */}
      {failures.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Failures Summary ({failures.length})
          </h3>
          <div className="space-y-3">
            {failureGroups.map(group => (
              <FailureGroupCard
                key={group.category}
                group={group}
                isExpanded={expandedFailureGroup.has(group.category)}
                onToggleExpand={() => toggleFailureGroup(group.category)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Overall Stats Card
// ============================================================================

interface OverallStatsCardProps {
  stats: OverallStats
  timeRemaining?: number
}

function OverallStatsCard({ stats, timeRemaining }: OverallStatsCardProps) {
  const StageIcon = stats.execution_stage === 'complete' ? CheckCircle :
                    stats.execution_stage === 'failed' ? XCircle : Clock

  return (
    <div className={`p-6 border-2 rounded-lg ${getStageBgColor(stats.execution_stage)}`}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Overall Progress
          </h3>
          <p className={`text-sm ${getStageColor(stats.execution_stage)} mt-1`}>
            {getStageLabel(stats.execution_stage)}
          </p>
        </div>
        <StageIcon className={`w-6 h-6 ${getStageColor(stats.execution_stage)} ${
          stats.execution_stage === 'execution' ? 'animate-pulse' : ''
        }`} />
      </div>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-sm text-gray-600 dark:text-gray-400 mb-2">
          <span>{stats.completed_scenarios} / {stats.total_scenarios} scenarios</span>
          <span>{stats.pass_rate.toFixed(1)}% pass rate</span>
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
          <div
            className={`h-3 rounded-full transition-all duration-500 ${
              stats.execution_stage === 'complete'
                ? 'bg-green-500'
                : stats.execution_stage === 'failed'
                ? 'bg-red-500'
                : 'bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500'
            }`}
            style={{ width: `${Math.min(100, (stats.completed_scenarios / Math.max(stats.total_scenarios, 1)) * 100)}%` }}
          />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="text-center p-3 bg-white/50 dark:bg-gray-900/50 rounded-lg">
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{stats.total_journeys}</p>
          <p className="text-xs text-gray-600 dark:text-gray-400">Journeys</p>
        </div>
        <div className="text-center p-3 bg-white/50 dark:bg-gray-900/50 rounded-lg">
          <p className="text-2xl font-bold text-green-600 dark:text-green-400">{stats.passed_scenarios}</p>
          <p className="text-xs text-gray-600 dark:text-gray-400">Passed</p>
        </div>
        <div className="text-center p-3 bg-white/50 dark:bg-gray-900/50 rounded-lg">
          <p className="text-2xl font-bold text-red-600 dark:text-red-400">{stats.failed_scenarios}</p>
          <p className="text-xs text-gray-600 dark:text-gray-400">Failed</p>
        </div>
        <div className="text-center p-3 bg-white/50 dark:bg-gray-900/50 rounded-lg">
          <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">{stats.pass_rate.toFixed(0)}%</p>
          <p className="text-xs text-gray-600 dark:text-gray-400">Pass Rate</p>
        </div>
        <div className="text-center p-3 bg-white/50 dark:bg-gray-900/50 rounded-lg">
          <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
            {formatTimeRemaining(timeRemaining)}
          </p>
          <p className="text-xs text-gray-600 dark:text-gray-400">Est. Time</p>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Stage Indicator
// ============================================================================

interface StageIndicatorProps {
  stage: ExecutionStage
  history: { stage: ExecutionStage; timestamp: string }[]
}

const STAGES: ExecutionStage[] = [
  'not_started',
  'parsing',
  'extraction',
  'generation',
  'execution',
  'processing',
  'updating',
  'complete'
]

function StageIndicator({ stage, history }: StageIndicatorProps) {
  const currentIndex = STAGES.indexOf(stage)

  return (
    <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
        Execution Progress
      </h4>
      <div className="flex items-center justify-between">
        {STAGES.map((s, index) => {
          const isCompleted = index < currentIndex
          const isCurrent = index === currentIndex
          const hasFailed = stage === 'failed'

          return (
            <div key={s} className="flex items-center">
              <div
                className={`
                  w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium
                  ${isCompleted ? 'bg-green-500 text-white' : ''}
                  ${isCurrent && !hasFailed ? 'bg-blue-500 text-white animate-pulse' : ''}
                  ${!isCompleted && !isCurrent ? 'bg-gray-300 dark:bg-gray-700 text-gray-500' : ''}
                  ${hasFailed && isCurrent ? 'bg-red-500 text-white' : ''}
                `}
              >
                {isCompleted ? '✓' : index + 1}
              </div>
              {index < STAGES.length - 1 && (
                <div
                  className={`
                    w-8 h-1 mx-1
                    ${isCompleted ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-700'}
                  `}
                />
              )}
            </div>
          )
        })}
      </div>
      <p className={`text-sm mt-3 ${getStageColor(stage)}`}>
        Current: {getStageLabel(stage)}
      </p>
    </div>
  )
}

// ============================================================================
// Journey Progress Card
// ============================================================================

interface JourneyProgressCardProps {
  journey: JourneyStats
  isExpanded: boolean
  onClick: () => void
  onToggleExpand: () => void
  onResultsClick?: () => void
  onFailuresClick?: () => void
}

function JourneyProgressCard({
  journey,
  isExpanded,
  onClick,
  onToggleExpand,
  onResultsClick,
  onFailuresClick
}: JourneyProgressCardProps) {
  const StatusIcon = journey.status === 'passed' ? CheckCircle :
                     journey.status === 'failed' ? XCircle : Clock

  return (
    <div
      className={`border-2 rounded-lg overflow-hidden transition-all duration-200 ${
        journey.status === 'passed'
          ? 'border-green-300 dark:border-green-700'
          : journey.status === 'failed'
          ? 'border-red-300 dark:border-red-700'
          : 'border-gray-300 dark:border-gray-700'
      }`}
    >
      {/* Header */}
      <div
        className="p-4 flex items-center gap-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
        onClick={onClick}
      >
        <StatusIcon className={`w-5 h-5 ${getStatusColor(journey.status)} ${
          journey.execution_stage === 'execution' ? 'animate-pulse' : ''
        }`} />

        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h4 className="font-semibold text-gray-900 dark:text-gray-100">
              {journey.journey_name}
            </h4>
            <span className={`text-xs px-2 py-0.5 rounded ${getStageBgColor(journey.execution_stage)} ${getStageColor(journey.execution_stage)}`}>
              {getStageLabel(journey.execution_stage)}
            </span>
          </div>

          <div className="flex items-center gap-4 mt-2 text-sm text-gray-600 dark:text-gray-400">
            <span>{journey.completed_scenarios} / {journey.total_scenarios} scenarios</span>
            <span className={getStatusColor(journey.status)}>
              {journey.pass_rate.toFixed(1)}% pass rate
            </span>
          </div>
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation()
            onToggleExpand()
          }}
          className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
        >
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-600" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-600" />
          )}
        </button>
      </div>

      {/* Progress Bar */}
      <div className="px-4 pb-3">
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-300 ${
              journey.status === 'passed'
                ? 'bg-green-500'
                : journey.status === 'failed'
                ? 'bg-red-500'
                : 'bg-blue-500'
            }`}
            style={{ width: `${journey.pass_rate}%` }}
          />
        </div>
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="border-t border-gray-200 dark:border-gray-700 p-4 space-y-3">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-gray-600 dark:text-gray-400">Passed</p>
              <p className="text-lg font-semibold text-green-600 dark:text-green-400">
                {journey.passed_scenarios}
              </p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400">Failed</p>
              <p className="text-lg font-semibold text-red-600 dark:text-red-400">
                {journey.failed_scenarios}
              </p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400">Remaining</p>
              <p className="text-lg font-semibold text-gray-600 dark:text-gray-400">
                {journey.total_scenarios - journey.completed_scenarios}
              </p>
            </div>
          </div>

          {/* Action Links */}
          <div className="flex items-center gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
            {journey.details_url && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onClick()
                }}
                className="flex items-center gap-1 text-sm text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-300"
              >
                <LinkIcon className="w-3 h-3" />
                View Details
              </button>
            )}
            {journey.results_url && journey.status !== 'pending' && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onResultsClick?.()
                }}
                className="flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
              >
                <LinkIcon className="w-3 h-3" />
                View Results
              </button>
            )}
            {journey.failures_url && journey.status === 'failed' && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onFailuresClick?.()
                }}
                className="flex items-center gap-1 text-sm text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300"
              >
                <AlertTriangle className="w-3 h-3" />
                View Failures
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Failure Group Card
// ============================================================================

interface FailureGroupCardProps {
  group: FailureGroup
  isExpanded: boolean
  onToggleExpand: () => void
}

function FailureGroupCard({ group, isExpanded, onToggleExpand }: FailureGroupCardProps) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={onToggleExpand}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-2xl">{group.icon}</span>
          <div className="text-left">
            <h4 className="font-semibold text-gray-900 dark:text-gray-100">
              {group.label}
            </h4>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {group.count} failure{group.count !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm">
            {group.bySeverity.critical > 0 && (
              <span className="px-2 py-0.5 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded">
                {group.bySeverity.critical} Critical
              </span>
            )}
            {group.bySeverity.high > 0 && (
              <span className="px-2 py-0.5 bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 rounded">
                {group.bySeverity.high} High
              </span>
            )}
          </div>
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-600" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-600" />
          )}
        </div>
      </button>

      {isExpanded && (
        <div className="border-t border-gray-200 dark:border-gray-700 p-4 space-y-2 max-h-96 overflow-y-auto">
          {group.failures.map(failure => (
            <div
              key={failure.id}
              className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
            >
              <div className="flex items-start justify-between mb-1">
                <p className="font-medium text-gray-900 dark:text-gray-100">
                  {failure.scenario}
                </p>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  failure.severity === 'critical' ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' :
                  failure.severity === 'high' ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300' :
                  failure.severity === 'medium' ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300' :
                  'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                }`}>
                  {failure.severity}
                </span>
              </div>
              <p className={`text-sm ${getSeverityColor(failure.severity)}`}>
                {failure.message}
              </p>
              {failure.selector && (
                <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 font-mono">
                  Selector: {failure.selector}
                </p>
              )}
              {failure.url && (
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                  {failure.url}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default ProgressTracker
