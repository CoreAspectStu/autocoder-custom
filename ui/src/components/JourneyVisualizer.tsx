/**
 * Journey Visualizer Component
 *
 * Interactive flow diagram for displaying and navigating UAT test journeys.
 * Shows test status, coverage, and allows journey selection and navigation.
 *
 * Features:
 * - Interactive journey flow diagram
 * - Test status indicators for each step
 * - Journey selection and navigation
 * - Journey metadata display
 * - Link to detailed test results
 */

import { useState, useMemo } from 'react'
import {
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle,
  ChevronRight,
  ChevronDown,
  Filter,
  Play,
  Eye,
  Info,
  Zap
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export type JourneyStatus = 'pending' | 'in_progress' | 'completed' | 'failed'
export type JourneyPhase = 'smoke' | 'functional' | 'journey' | 'regression'

export interface JourneyStep {
  step_id: string
  step_name: string
  scenario: string
  description: string
  test_file?: string
  status: JourneyStatus
  test_result?: {
    test_id: string
    status: string
    score?: number
    error?: string
  }
  dependencies: string[]  // Step IDs that must complete first
  completed_at?: string
}

export interface Journey {
  journey_id: string
  journey_name: string
  phase: JourneyPhase
  description: string
  steps: JourneyStep[]
  total_steps: number
  completed_steps: number
  failed_steps: number
  status: JourneyStatus
  coverage_percentage: number
  metadata?: {
    priority?: string
    estimated_duration?: number
    tags?: string[]
  }
}

interface JourneyVisualizerProps {
  journeys: Journey[]
  onJourneySelect?: (journey: Journey) => void
  onStepClick?: (journey: Journey, step: JourneyStep) => void
  autoSelectFirst?: boolean
}

// ============================================================================
// Helpers
// ============================================================================

function getPhaseColor(phase: JourneyPhase): string {
  const colors = {
    smoke: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300',
    functional: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
    journey: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
    regression: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300'
  }
  return colors[phase] || colors.functional
}

function getPhaseLabel(phase: JourneyPhase): string {
  return phase.charAt(0).toUpperCase() + phase.slice(1)
}

function getStatusIcon(status: JourneyStatus) {
  const icons = {
    pending: Clock,
    in_progress: Zap,
    completed: CheckCircle,
    failed: XCircle
  }
  return icons[status] || Clock
}

function getStatusColor(status: JourneyStatus): string {
  const colors = {
    pending: 'text-gray-400',
    in_progress: 'text-blue-500',
    completed: 'text-green-500',
    failed: 'text-red-500'
  }
  return colors[status] || 'text-gray-400'
}

function getStepConnectorColor(status: JourneyStatus): string {
  const colors = {
    pending: 'border-gray-300 dark:border-gray-700',
    in_progress: 'border-blue-500',
    completed: 'border-green-500',
    failed: 'border-red-500'
  }
  return colors[status] || 'border-gray-300'
}

// ============================================================================
// Components
// ============================================================================

export function JourneyVisualizer({
  journeys,
  onJourneySelect,
  onStepClick,
  autoSelectFirst = false
}: JourneyVisualizerProps) {
  const [selectedJourney, setSelectedJourney] = useState<Journey | null>(null)
  const [expandedJourneys, setExpandedJourneys] = useState<Set<string>>(new Set())
  const [filterPhase, setFilterPhase] = useState<JourneyPhase | 'all'>('all')
  const [filterStatus, setFilterStatus] = useState<JourneyStatus | 'all'>('all')

  // Auto-select first journey if enabled
  useMemo(() => {
    if (autoSelectFirst && journeys.length > 0 && !selectedJourney) {
      setSelectedJourney(journeys[0])
      if (onJourneySelect) {
        onJourneySelect(journeys[0])
      }
    }
  }, [autoSelectFirst, journeys, selectedJourney, onJourneySelect])

  // Filter journeys
  const filteredJourneys = useMemo(() => {
    return journeys.filter(journey => {
      if (filterPhase !== 'all' && journey.phase !== filterPhase) return false
      if (filterStatus !== 'all' && journey.status !== filterStatus) return false
      return true
    })
  }, [journeys, filterPhase, filterStatus])

  // Group journeys by phase
  const journeysByPhase = useMemo(() => {
    const groups: Record<string, Journey[]> = {
      smoke: [],
      functional: [],
      journey: [],
      regression: []
    }
    filteredJourneys.forEach(journey => {
      groups[journey.phase].push(journey)
    })
    return groups
  }, [filteredJourneys])

  const toggleJourneyExpanded = (journeyId: string) => {
    setExpandedJourneys(prev => {
      const newSet = new Set(prev)
      if (newSet.has(journeyId)) {
        newSet.delete(journeyId)
      } else {
        newSet.add(journeyId)
      }
      return newSet
    })
  }

  const handleJourneyClick = (journey: Journey) => {
    setSelectedJourney(journey)
    if (onJourneySelect) {
      onJourneySelect(journey)
    }
  }

  const handleStepClick = (journey: Journey, step: JourneyStep) => {
    if (onStepClick) {
      onStepClick(journey, step)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header with Filters */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
          UAT Test Journeys
        </h2>

        <div className="flex items-center gap-2">
          {/* Phase Filter */}
          <select
            value={filterPhase}
            onChange={(e) => setFilterPhase(e.target.value as JourneyPhase | 'all')}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300"
          >
            <option value="all">All Phases</option>
            <option value="smoke">Smoke Tests</option>
            <option value="functional">Functional Tests</option>
            <option value="journey">Journey Tests</option>
            <option value="regression">Regression Tests</option>
          </select>

          {/* Status Filter */}
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as JourneyStatus | 'all')}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300"
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      {/* Summary Stats */}
      <JourneySummaryStats journeys={filteredJourneys} />

      {/* Phase Groups */}
      {Object.entries(journeysByPhase).map(([phase, phaseJourneys]) => {
        if (phaseJourneys.length === 0) return null

        return (
          <div key={phase} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <div className={`p-4 ${getPhaseColor(phase as JourneyPhase)}`}>
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">
                  {getPhaseLabel(phase as JourneyPhase)} Tests
                </h3>
                <span className="text-sm opacity-75">
                  {phaseJourneys.length} journey{phaseJourneys.length > 1 ? 's' : ''}
                </span>
              </div>
            </div>

            <div className="p-4 space-y-3">
              {phaseJourneys.map((journey) => (
                <JourneyCard
                  key={journey.journey_id}
                  journey={journey}
                  isExpanded={expandedJourneys.has(journey.journey_id)}
                  isSelected={selectedJourney?.journey_id === journey.journey_id}
                  onClick={() => handleJourneyClick(journey)}
                  onToggleExpand={() => toggleJourneyExpanded(journey.journey_id)}
                  onStepClick={handleStepClick}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ============================================================================
// Journey Card Component
// ============================================================================

interface JourneyCardProps {
  journey: Journey
  isExpanded: boolean
  isSelected: boolean
  onClick: () => void
  onToggleExpand: () => void
  onStepClick: (journey: Journey, step: JourneyStep) => void
}

function JourneyCard({
  journey,
  isExpanded,
  isSelected,
  onClick,
  onToggleExpand,
  onStepClick
}: JourneyCardProps) {
  const StatusIcon = getStatusIcon(journey.status)

  return (
    <div
      className={`border-2 rounded-lg overflow-hidden transition-all duration-200 ${
        isSelected
          ? 'border-purple-500 shadow-lg'
          : journey.status === 'completed'
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
        {/* Status Icon */}
        <div className={`p-2 rounded-lg ${
          journey.status === 'completed'
            ? 'bg-green-100 dark:bg-green-900/30'
            : journey.status === 'failed'
            ? 'bg-red-100 dark:bg-red-900/30'
            : 'bg-gray-100 dark:bg-gray-800'
        }`}>
          <StatusIcon className={`w-5 h-5 ${getStatusColor(journey.status)} ${
            journey.status === 'in_progress' ? 'animate-pulse' : ''
          }`} />
        </div>

        {/* Journey Info */}
        <div className="flex-1">
          <h4 className="font-semibold text-gray-900 dark:text-gray-100">
            {journey.journey_name}
          </h4>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {journey.description}
          </p>

          {/* Progress Bar */}
          <div className="mt-2">
            <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
              <span>{journey.completed_steps} / {journey.total_steps} steps</span>
              <span>{journey.coverage_percentage.toFixed(0)}% complete</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-300 ${
                  journey.status === 'completed'
                    ? 'bg-green-500'
                    : journey.status === 'failed'
                    ? 'bg-red-500'
                    : 'bg-blue-500'
                }`}
                style={{ width: `${journey.coverage_percentage}%` }}
              />
            </div>
          </div>
        </div>

        {/* Expand/Collapse */}
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

      {/* Expanded Steps */}
      {isExpanded && (
        <div className="border-t border-gray-200 dark:border-gray-700 p-4">
          <JourneyStepsFlow
            journey={journey}
            onStepClick={onStepClick}
          />
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Journey Steps Flow Diagram
// ============================================================================

interface JourneyStepsFlowProps {
  journey: Journey
  onStepClick?: (journey: Journey, step: JourneyStep) => void
}

function JourneyStepsFlow({ journey, onStepClick }: JourneyStepsFlowProps) {
  const [hoveredStep, setHoveredStep] = useState<string | null>(null)

  // Sort steps topologically based on dependencies
  const sortedSteps = useMemo(() => {
    const sorted: JourneyStep[] = []
    const visited = new Set<string>()
    const stepsMap = new Map(journey.steps.map(s => [s.step_id, s]))

    const visit = (stepId: string) => {
      if (visited.has(stepId)) return
      visited.add(stepId)

      const step = stepsMap.get(stepId)
      if (step) {
        // First visit dependencies
        step.dependencies.forEach(visit)
        sorted.push(step)
      }
    }

    journey.steps.forEach(step => visit(step.step_id))
    return sorted
  }, [journey.steps])

  return (
    <div className="space-y-4">
      {sortedSteps.map((step, index) => {
        const isClickable = onStepClick && step.status !== 'pending'
        const StatusIcon = getStatusIcon(step.status)
        const isLast = index === sortedSteps.length - 1

        return (
          <div key={step.step_id} className="relative">
            {/* Step Node */}
            <div
              className={`
                flex items-center gap-3 p-3 border-2 rounded-lg transition-all duration-200
                ${hoveredStep === step.step_id ? 'shadow-lg scale-105' : ''}
                ${step.status === 'completed'
                  ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20'
                  : step.status === 'failed'
                  ? 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20'
                  : step.status === 'in_progress'
                  ? 'border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800'
                }
                ${isClickable ? 'cursor-pointer hover:shadow-md' : ''}
              `}
              onMouseEnter={() => setHoveredStep(step.step_id)}
              onMouseLeave={() => setHoveredStep(null)}
              onClick={() => isClickable && onStepClick && onStepClick(journey, step)}
            >
              <StatusIcon className={`w-5 h-5 ${getStatusColor(step.status)} ${
                step.status === 'in_progress' ? 'animate-pulse' : ''
              }`} />

              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h5 className="font-semibold text-gray-900 dark:text-gray-100">
                    {step.step_name}
                  </h5>
                  {step.test_file && (
                    <span className="text-xs text-gray-500 bg-gray-200 dark:bg-gray-700 px-2 py-0.5 rounded">
                      {step.test_file}
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  {step.scenario}
                </p>
              </div>

              {/* Step Actions */}
              {step.test_result && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      // View test result
                      console.log('View test result:', step.test_result)
                    }}
                    className="p-1 hover:bg-white dark:hover:bg-gray-800 rounded transition-colors"
                    title="View test result"
                  >
                    <Eye className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  </button>
                </div>
              )}

              {/* Step Details */}
              {(step.description || step.dependencies.length > 0) && (
                <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
                  {step.dependencies.length > 0 && (
                    <p className="mb-1">
                      Requires: {step.dependencies.join(', ')}
                    </p>
                  )}
                  {step.description && (
                    <p>{step.description}</p>
                  )}
                </div>
              )}
            </div>

            {/* Connector Line */}
            {!isLast && (
              <div className="ml-8 h-6 flex items-center">
                <div className={`w-0.5 h-full ${getStepConnectorColor(step.status)}`} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ============================================================================
// Summary Stats Component
// ============================================================================

interface JourneySummaryStatsProps {
  journeys: Journey[]
}

function JourneySummaryStats({ journeys }: JourneySummaryStatsProps) {
  const stats = useMemo(() => {
    const total = journeys.length
    const completed = journeys.filter((j: Journey) => j.status === 'completed').length
    const failed = journeys.filter((j: Journey) => j.status === 'failed').length
    const inProgress = journeys.filter((j: Journey) => j.status === 'in_progress').length
    const pending = journeys.filter((j: Journey) => j.status === 'pending').length

    const totalSteps = journeys.reduce((sum: number, j: Journey) => sum + j.total_steps, 0)
    const completedSteps = journeys.reduce((sum: number, j: Journey) => sum + j.completed_steps, 0)

    // Count by phase
    const byPhase = journeys.reduce((acc: Record<JourneyPhase, number>, j: Journey) => {
      acc[j.phase] = (acc[j.phase] || 0) + 1
      return acc
    }, {} as Record<JourneyPhase, number>)

    // Average coverage
    const avgCoverage = journeys.length > 0
      ? journeys.reduce((sum: number, j: Journey) => sum + j.coverage_percentage, 0) / journeys.length
      : 0

    return {
      total,
      completed,
      failed,
      inProgress,
      pending,
      totalSteps,
      completedSteps,
      byPhase,
      avgCoverage
    }
  }, [journeys])

  return (
    <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
      <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-center">
        <p className="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.total}</p>
        <p className="text-xs text-gray-600 dark:text-gray-400">Journeys</p>
      </div>

      <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg text-center">
        <p className="text-lg font-bold text-green-600 dark:text-green-400">{stats.completed}</p>
        <p className="text-xs text-green-700 dark:text-green-300">Completed</p>
      </div>

      <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg text-center">
        <p className="text-lg font-bold text-red-600 dark:text-red-400">{stats.failed}</p>
        <p className="text-xs text-red-700 dark:text-red-300">Failed</p>
      </div>

      <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-center">
        <p className="text-lg font-bold text-blue-600 dark:text-blue-400">{stats.inProgress}</p>
        <p className="text-xs text-blue-700 dark:text-blue-300">Running</p>
      </div>

      <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg text-center">
        <p className="text-lg font-bold text-purple-600 dark:text-purple-400">{stats.avgCoverage.toFixed(0)}%</p>
        <p className="text-xs text-purple-700 dark:text-purple-300">Avg Coverage</p>
      </div>

      <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg text-center">
        <p className="text-lg font-bold text-gray-900 dark:text-gray-100">
          {stats.completedSteps} / {stats.totalSteps}
        </p>
        <p className="text-xs text-gray-600 dark:text-gray-400">Steps Done</p>
      </div>
    </div>
  )
}

// ============================================================================
// Journey Legend Component
// ============================================================================

interface JourneyLegendProps {
  onJourneySelect?: (phase: JourneyPhase | 'all') => void
}

export function JourneyLegend({ onJourneySelect }: JourneyLegendProps) {
  const phases: (JourneyPhase | 'all')[] = ['all', 'smoke', 'functional', 'journey', 'regression']

  return (
    <div className="flex items-center gap-4 flex-wrap">
      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Quick Filter:</span>
      {phases.map((phase) => (
        <button
          key={phase}
          onClick={() => onJourneySelect?.(phase as JourneyPhase | 'all')}
          className={`
            px-3 py-1 text-sm rounded-full border transition-all duration-200
            ${phase === 'all'
              ? 'border-gray-400 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300'
              : `border-gray-300 dark:border-gray-600 ${getPhaseColor(phase as JourneyPhase)}`
            }
            hover:shadow-md
          `}
        >
          {phase === 'all' ? 'All' : getPhaseLabel(phase as JourneyPhase)}
        </button>
      ))}
    </div>
  )
}

// ============================================================================
// Journey Progress Indicator
// ============================================================================

interface JourneyProgressProps {
  journey: Journey
  showDetails?: boolean
}

export function JourneyProgress({ journey, showDetails = false }: JourneyProgressProps) {
  const StatusIcon = getStatusIcon(journey.status)

  return (
    <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <StatusIcon className={`w-5 h-5 ${getStatusColor(journey.status)}`} />
        <div className="flex-1">
          <h4 className="font-semibold text-gray-900 dark:text-gray-100">
            {journey.journey_name}
          </h4>
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {getPhaseLabel(journey.phase)} Phase
          </p>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
          <span>{journey.completed_steps} / {journey.total_steps} tests</span>
          <span>{journey.coverage_percentage.toFixed(0)}% complete</span>
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-300 ${
              journey.status === 'completed'
                ? 'bg-green-500'
                : journey.status === 'failed'
                ? 'bg-red-500'
                : 'bg-blue-500'
            }`}
            style={{ width: `${journey.coverage_percentage}%` }}
          />
        </div>
      </div>

      {/* Details */}
      {showDetails && (
        <div className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
          <p>Status: <span className={`capitalize ${getStatusColor(journey.status)}`}>{journey.status}</span></p>
          <p>Steps: {journey.completed_steps} passed, {journey.failed_steps} failed</p>
          {journey.metadata?.estimated_duration && (
            <p>Est. duration: {journey.metadata.estimated_duration}s</p>
          )}
        </div>
      )}
    </div>
  )
}

export default JourneyVisualizer
