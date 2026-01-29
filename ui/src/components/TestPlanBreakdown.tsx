/**
 * Test Plan Breakdown Component
 *
 * Displays test plan organized by:
 * - Journey (authentication, payment, onboarding, etc.)
 * - Phase (smoke, functional, regression, UAT)
 *
 * Shows test counts per group and a journey-phase matrix.
 *
 * Feature #15: Display test plan breakdown by journey and phase
 */

import { useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Grid3x3,
  List,
  CheckCircle2,
} from 'lucide-react'
import type {
  GenerateTestPlanResponse,
  JourneyProposal,
  TestFrameworkProposal,
  TestScenario,
} from '../hooks/useGenerateTestPlan'

interface TestPlanBreakdownProps {
  testPlan: GenerateTestPlanResponse
}

type ViewMode = 'summary' | 'matrix' | 'detailed'

export function TestPlanBreakdown({ testPlan }: TestPlanBreakdownProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('summary')
  const [expandedJourneys, setExpandedJourneys] = useState<Set<string>>(new Set())
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set())

  // Toggle journey expansion
  const toggleJourney = (journey: string) => {
    setExpandedJourneys((prev) => {
      const next = new Set(prev)
      if (next.has(journey)) {
        next.delete(journey)
      } else {
        next.add(journey)
      }
      return next
    })
  }

  // Toggle phase expansion
  const togglePhase = (phase: string) => {
    setExpandedPhases((prev) => {
      const next = new Set(prev)
      if (next.has(phase)) {
        next.delete(phase)
      } else {
        next.add(phase)
      }
      return next
    })
  }

  // Build journey-phase matrix
  const buildMatrix = () => {
    const journeys = testPlan.journeys_identified
    const phases = testPlan.recommended_phases

    // Create matrix: journey x phase
    const matrix: Record<string, Record<string, number>> = {}

    journeys.forEach((j) => {
      matrix[j.journey] = {}
      phases.forEach((p) => {
        // Count tests for this journey-phase combination
        const count = testPlan.test_scenarios.filter(
          (t) => t.journey === j.journey && t.phase === p.phase
        ).length
        matrix[j.journey][p.phase] = count
      })
    })

    return { journeys, phases, matrix }
  }

  // Get tests for a specific journey-phase combination
  const getTestsForJourneyPhase = (journey: string, phase: string): TestScenario[] => {
    return testPlan.test_scenarios.filter(
      (t) => t.journey === journey && t.phase === phase
    )
  }

  // Get tests for a journey
  const getTestsForJourney = (journey: string): TestScenario[] => {
    return testPlan.test_scenarios.filter((t) => t.journey === journey)
  }

  // Get tests for a phase
  const getTestsForPhase = (phase: string): TestScenario[] => {
    return testPlan.test_scenarios.filter((t) => t.phase === phase)
  }

  const { journeys, phases, matrix } = buildMatrix()

  // ============================================================================
  // Render Functions
  // ============================================================================

  const renderSummary = () => (
    <div className="space-y-4">
      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-purple-50 dark:bg-purple-900/20 p-4 rounded-lg border-l-4 border-purple-500">
          <p className="text-xs text-purple-600 dark:text-purple-400 font-medium uppercase tracking-wide">
            Total Tests
          </p>
          <p className="text-3xl font-bold text-purple-700 dark:text-purple-300">
            {testPlan.test_scenarios.length}
          </p>
        </div>

        <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg border-l-4 border-blue-500">
          <p className="text-xs text-blue-600 dark:text-blue-400 font-medium uppercase tracking-wide">
            User Journeys
          </p>
          <p className="text-3xl font-bold text-blue-700 dark:text-blue-300">
            {testPlan.journeys_identified.length}
          </p>
        </div>

        <div className="bg-green-50 dark:bg-green-900/20 p-4 rounded-lg border-l-4 border-green-500">
          <p className="text-xs text-green-600 dark:text-green-400 font-medium uppercase tracking-wide">
            Test Phases
          </p>
          <p className="text-3xl font-bold text-green-700 dark:text-green-300">
            {testPlan.recommended_phases.length}
          </p>
        </div>
      </div>

      {/* Grouped by Journey */}
      <div className="space-y-2">
        <h4 className="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
          <List className="w-5 h-5 text-blue-500" />
          By User Journey
        </h4>
        {testPlan.journeys_identified.map((journey) => {
          const isExpanded = expandedJourneys.has(journey.journey)
          const tests = getTestsForJourney(journey.journey)

          return (
            <div
              key={journey.journey}
              className="border-2 border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
            >
              <button
                onClick={() => toggleJourney(journey.journey)}
                className="w-full flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {isExpanded ? (
                    <ChevronUp className="w-5 h-5 text-gray-500" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-gray-500" />
                  )}
                  <span className="font-semibold text-gray-900 dark:text-gray-100">
                    {journey.journey}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    {journey.test_count} tests
                  </span>
                  <span className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full">
                    {journey.phases.join(', ')}
                  </span>
                </div>
              </button>

              {isExpanded && (
                <div className="p-3 space-y-2 bg-white dark:bg-gray-900">
                  {tests.slice(0, 10).map((test) => (
                    <div
                      key={test.id}
                      className="text-sm p-2 bg-gray-50 dark:bg-gray-800 rounded border-l-2 border-purple-500"
                    >
                      <div className="font-medium text-gray-900 dark:text-gray-100">
                        {test.scenario}
                      </div>
                      <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                        Phase: {test.phase} • Type: {test.test_type}
                      </div>
                    </div>
                  ))}
                  {tests.length > 10 && (
                    <div className="text-xs text-gray-500 dark:text-gray-400 text-center pt-2">
                      ... and {tests.length - 10} more tests
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Grouped by Phase */}
      <div className="space-y-2">
        <h4 className="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
          <Grid3x3 className="w-5 h-5 text-green-500" />
          By Test Phase
        </h4>
        {testPlan.recommended_phases.map((phase) => {
          const isExpanded = expandedPhases.has(phase.phase)
          const tests = getTestsForPhase(phase.phase)

          return (
            <div
              key={phase.phase}
              className="border-2 border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
            >
              <button
                onClick={() => togglePhase(phase.phase)}
                className="w-full flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {isExpanded ? (
                    <ChevronUp className="w-5 h-5 text-gray-500" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-gray-500" />
                  )}
                  <span className="font-semibold text-gray-900 dark:text-gray-100">
                    {phase.phase}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    {phase.test_count} tests
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400 max-w-xs truncate">
                    {phase.description}
                  </span>
                </div>
              </button>

              {isExpanded && (
                <div className="p-3 space-y-2 bg-white dark:bg-gray-900">
                  {tests.slice(0, 10).map((test) => (
                    <div
                      key={test.id}
                      className="text-sm p-2 bg-gray-50 dark:bg-gray-800 rounded border-l-2 border-green-500"
                    >
                      <div className="font-medium text-gray-900 dark:text-gray-100">
                        {test.scenario}
                      </div>
                      <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                        Journey: {test.journey} • Type: {test.test_type}
                      </div>
                    </div>
                  ))}
                  {tests.length > 10 && (
                    <div className="text-xs text-gray-500 dark:text-gray-400 text-center pt-2">
                      ... and {tests.length - 10} more tests
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )

  const renderMatrix = () => {
    return (
      <div className="space-y-4">
        <div className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          <p>
            Matrix showing test count for each journey-phase combination.
            Empty cells indicate no tests for that combination.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-gray-100 dark:bg-gray-800">
                <th className="p-3 text-left font-semibold text-gray-900 dark:text-gray-100 border-2 border-gray-300 dark:border-gray-600">
                  Journey
                </th>
                {phases.map((phase) => (
                  <th
                    key={phase.phase}
                    className="p-3 text-center font-semibold text-gray-900 dark:text-gray-100 border-2 border-gray-300 dark:border-gray-600 min-w-[100px]"
                  >
                    <div className="text-sm">{phase.phase}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 font-normal">
                      {phase.test_count} total
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {journeys.map((journey) => (
                <tr key={journey.journey} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                  <td className="p-3 font-medium text-gray-900 dark:text-gray-100 border-2 border-gray-300 dark:border-gray-600">
                    <div>{journey.journey}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {journey.test_count} total
                    </div>
                  </td>
                  {phases.map((phase) => {
                    const count = matrix[journey.journey][phase.phase] || 0
                    const hasTests = count > 0

                    return (
                      <td
                        key={phase.phase}
                        className={`p-3 text-center border-2 border-gray-300 dark:border-gray-600 ${
                          hasTests
                            ? 'bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 font-semibold'
                            : 'bg-gray-50 dark:bg-gray-900 text-gray-400 dark:text-gray-600'
                        }`}
                      >
                        {count > 0 ? count : '—'}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Matrix Legend */}
        <div className="flex items-center gap-6 text-sm mt-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-purple-50 dark:bg-purple-900/20 border-2 border-gray-300 dark:border-gray-600"></div>
            <span className="text-gray-700 dark:text-gray-300">Has tests</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-gray-50 dark:bg-gray-900 border-2 border-gray-300 dark:border-gray-600"></div>
            <span className="text-gray-700 dark:text-gray-300">No tests</span>
          </div>
        </div>
      </div>
    )
  }

  const renderDetailed = () => {
    return (
      <div className="space-y-4">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Detailed breakdown showing journey-phase combinations with sample tests.
        </p>

        {journeys.map((journey) => (
          <div key={journey.journey} className="border-2 border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border-b-2 border-gray-200 dark:border-gray-700">
              <h4 className="font-semibold text-lg text-gray-900 dark:text-gray-100">
                {journey.journey}
              </h4>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {journey.test_count} tests across {journey.phases.length} phases
              </p>
            </div>

            <div className="divide-y-2 divide-gray-200 dark:divide-gray-700">
              {phases.map((phase) => {
                const tests = getTestsForJourneyPhase(journey.journey, phase.phase)

                if (tests.length === 0) return null

                return (
                  <div key={phase.phase} className="p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <CheckCircle2 className="w-5 h-5 text-green-500" />
                      <h5 className="font-semibold text-gray-900 dark:text-gray-100">
                        {phase.phase}
                      </h5>
                      <span className="text-sm text-gray-600 dark:text-gray-400">
                        ({tests.length} tests)
                      </span>
                    </div>

                    <div className="space-y-2">
                      {tests.slice(0, 5).map((test) => (
                        <div
                          key={test.id}
                          className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border-l-4 border-purple-500"
                        >
                          <div className="font-medium text-gray-900 dark:text-gray-100">
                            {test.scenario}
                          </div>
                          <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                            {test.description}
                          </div>
                          <div className="flex gap-2 mt-2">
                            <span className="text-xs px-2 py-1 bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 rounded">
                              {test.test_type}
                            </span>
                          </div>
                        </div>
                      ))}
                      {tests.length > 5 && (
                        <div className="text-xs text-gray-500 dark:text-gray-400 text-center py-2">
                          ... and {tests.length - 5} more tests for {journey.journey} / {phase.phase}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    )
  }

  // ============================================================================
  // Main Render
  // ============================================================================

  return (
    <div className="space-y-4">
      {/* View Mode Toggle */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Test Plan Breakdown
        </h3>
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode('summary')}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              viewMode === 'summary'
                ? 'bg-purple-500 text-white'
                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
            }`}
          >
            Summary
          </button>
          <button
            onClick={() => setViewMode('matrix')}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              viewMode === 'matrix'
                ? 'bg-purple-500 text-white'
                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
            }`}
          >
            Matrix
          </button>
          <button
            onClick={() => setViewMode('detailed')}
            className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              viewMode === 'detailed'
                ? 'bg-purple-500 text-white'
                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
            }`}
          >
            Detailed
          </button>
        </div>
      </div>

      {/* View Content */}
      <div className="bg-white dark:bg-gray-900 rounded-lg p-6 border-2 border-gray-200 dark:border-gray-700">
        {viewMode === 'summary' && renderSummary()}
        {viewMode === 'matrix' && renderMatrix()}
        {viewMode === 'detailed' && renderDetailed()}
      </div>
    </div>
  )
}
