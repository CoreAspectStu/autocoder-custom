/**
 * UAT Test Planning Component
 *
 * Orchestrates the conversational test planning flow:
 * 1. Gathers project context
 * 2. Detects blockers
 * 3. Asks user about blocker configuration
 * 4. Generates test plan
 * 5. Presents plan for approval
 *
 * This is the main entry point for UAT test planning from the UI.
 */

import { useState, useEffect } from 'react'
import { Bot, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import { BlockerQuestions, useBlockerDetection, type BlockerConfig } from './BlockerQuestions'
import { TestPlanBreakdown } from './TestPlanBreakdown'

// ============================================================================
// Types
// ============================================================================

type PlanningStep =
  | 'context'
  | 'blockers'
  | 'generating'
  | 'review'
  | 'complete'

interface ProjectContext {
  has_spec: boolean
  completed_features_count: number
  uat_cycles_count: number
}

// ============================================================================
// Component
// ============================================================================

interface UATTestPlanningProps {
  projectName: string
  onComplete?: () => void
  onCancel?: () => void
}

export function UATTestPlanning({ projectName, onComplete, onCancel }: UATTestPlanningProps) {
  const [step, setStep] = useState<PlanningStep>('context')
  const [context, setContext] = useState<ProjectContext | null>(null)
  const [blockers, setBlockers] = useState<BlockerConfig[]>([])
  const [testPlan, setTestPlan] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const { detectBlockers, configureBlockers, isLoading: blockersLoading } = useBlockerDetection()

  // Step 1: Gather project context
  useEffect(() => {
    if (step === 'context') {
      gatherContext()
    }
  }, [step])

  const gatherContext = async () => {
    try {
      const response = await fetch(`/api/uat/context/${projectName}`)
      if (!response.ok) throw new Error('Failed to gather context')

      const data = await response.json()
      setContext({
        has_spec: data.has_spec,
        completed_features_count: data.completed_features_count,
        uat_cycles_count: data.uat_cycles_count,
      })

      // Move to blocker detection
      setStep('blockers')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to gather context')
    }
  }

  // Step 2: Detect blockers
  useEffect(() => {
    if (step === 'blockers' && context && blockers.length === 0) {
      detectBlockersForProject()
    }
  }, [step, context])

  const detectBlockersForProject = async () => {
    try {
      const result = await detectBlockers(projectName)
      setBlockers(result.blockers_detected)

      // If no blockers, skip to generation
      if (result.blockers_detected.length === 0) {
        generateTestPlan({})
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to detect blockers')
    }
  }

  // Step 3: Configure blockers and generate plan
  const handleBlockersConfigured = async (configuredBlockers: BlockerConfig[]) => {
    try {
      await configureBlockers(projectName, configuredBlockers)
      setBlockers(configuredBlockers)

      // Generate test plan with blocker configuration
      const blockerConfig = configuredBlockers.reduce((acc, b) => {
        if (b.action) {
          acc[b.blocker_type] = b.action
        }
        return acc
      }, {} as Record<string, string>)

      generateTestPlan(blockerConfig)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to configure blockers')
    }
  }

  // Step 4: Generate test plan
  const generateTestPlan = async (blockerConfig: Record<string, string>) => {
    setStep('generating')
    setError(null)

    try {
      const response = await fetch('/api/uat/generate-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_name: projectName,
          blocker_config: blockerConfig,
        }),
      })

      if (!response.ok) throw new Error('Failed to generate test plan')

      const plan = await response.json()
      setTestPlan(plan)
      setStep('review')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate test plan')
      setStep('blockers')
    }
  }

  // Step 5: Complete planning - approve plan and create tests
  const handleApprovePlan = async () => {
    if (!testPlan?.cycle_id) {
      setError('No test plan to approve')
      return
    }

    setStep('generating')
    setError(null)

    try {
      // Call approve-plan endpoint to create UAT tests
      const response = await fetch(`/api/uat/approve-plan/${testPlan.cycle_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to approve test plan' }))
        throw new Error(errorData.detail || 'Failed to approve test plan')
      }

      const result = await response.json()

      console.log(`✅ Created ${result.tests_created} UAT tests`)
      console.log(`   Test IDs: ${result.test_ids.slice(0, 5).join(', ')}${result.test_ids.length > 5 ? '...' : ''}`)

      setStep('complete')
      onComplete?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve test plan')
      setStep('review')
    }
  }

  // ============================================================================
  // Render
  // ============================================================================

  if (error) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-3 text-red-600 dark:text-red-400">
          <AlertCircle className="w-6 h-6" />
          <h3 className="text-lg font-semibold">Error</h3>
        </div>
        <p className="text-gray-700 dark:text-gray-300">{error}</p>
        <button
          onClick={onCancel}
          className="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
        >
          Close
        </button>
      </div>
    )
  }

  if (step === 'context' || blockersLoading) {
    return (
      <div className="flex flex-col items-center gap-4 p-12">
        <Loader2 className="w-12 h-12 text-purple-500 animate-spin" />
        <p className="text-gray-600 dark:text-gray-400">Analyzing project...</p>
      </div>
    )
  }

  if (step === 'blockers' && blockers.length > 0) {
    return (
      <div className="flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-center gap-3 p-4 bg-purple-50 dark:bg-purple-900/20 border-l-4 border-purple-500">
          <Bot className="w-6 h-6 text-purple-600 dark:text-purple-400" />
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-gray-100">
              Blocker Detection
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              I found {blockers.length} potential blocker(s) that may prevent test execution
            </p>
          </div>
        </div>

        {/* Blocker Questions */}
        <BlockerQuestions
          projectName={projectName}
          blockers={blockers}
          onConfigure={handleBlockersConfigured}
        />
      </div>
    )
  }

  if (step === 'generating') {
    return (
      <div className="flex flex-col items-center gap-4 p-12">
        <Loader2 className="w-12 h-12 text-purple-500 animate-spin" />
        <p className="text-gray-600 dark:text-gray-400">
          {testPlan ? 'Creating UAT tests...' : 'Generating test plan...'}
        </p>
        <p className="text-sm text-gray-500 dark:text-gray-500">
          {testPlan
            ? 'Please wait while I create your test tasks'
            : 'This may take a moment while I analyze your project'
          }
        </p>
      </div>
    )
  }

  if (step === 'review' && testPlan) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-3 text-green-600 dark:text-green-400">
          <CheckCircle className="w-6 h-6" />
          <h3 className="text-lg font-semibold">Test Plan Ready!</h3>
        </div>

        <div className="p-4 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">
            {testPlan.message}
          </p>
        </div>

        {/* Feature #15: Display test plan breakdown by journey and phase */}
        <TestPlanBreakdown testPlan={testPlan} />

        <div className="flex gap-3">
          <button
            onClick={handleApprovePlan}
            className="flex-1 px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors font-semibold"
          >
            Approve & Start Testing
          </button>
          <button
            onClick={onCancel}
            className="px-4 py-2 border-2 border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  if (step === 'complete') {
    return (
      <div className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-3 text-green-600 dark:text-green-400">
          <CheckCircle className="w-6 h-6" />
          <h3 className="text-lg font-semibold">Planning Complete!</h3>
        </div>
        <p className="text-gray-700 dark:text-gray-300">
          Your UAT test plan has been configured and saved. You can now start test execution.
        </p>
        <button
          onClick={onCancel}
          className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors"
        >
          Close
        </button>
      </div>
    )
  }

  return null
}
