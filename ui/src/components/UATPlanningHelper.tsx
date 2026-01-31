/**
 * UAT Planning Helper Component
 *
 * Displays in AssistantPanel when in UAT mode to guide test planning:
 * 1. Shows context gathering progress
 * 2. Displays test framework proposal (conversational interface)
 * 3. Allows user to confirm, modify, or reject the plan naturally
 */

import { useEffect, useState } from 'react'
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  FileText,
  List,
  History,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ThumbsUp,
  ThumbsDown,
  MessageSquare,
  Send
} from 'lucide-react'
import {
  useUATProjectContext,
  isContextComplete,
  getMissingContextItems,
  type UATProjectContext
} from '../hooks/useUATProjectContext'
import { useUATMode } from '../contexts/UATModeContext'
import { useGenerateTestPlan, type GenerateTestPlanResponse } from '../hooks/useGenerateTestPlan'
import { useModifyTestPlan, type ModifyTestPlanResponse } from '../hooks/useModifyTestPlan'
import { useApproveTestPlan, type ApproveTestPlanResponse } from '../hooks/useApproveTestPlan'

interface UATPlanningHelperProps {
  projectName: string | undefined
  onContextReady?: (context: UATProjectContext) => void
  onPlanGenerated?: (plan: GenerateTestPlanResponse) => void
}

type Stage = 'gathering' | 'ready' | 'generating' | 'proposal' | 'confirming_rejection' | 'confirmed'

export function UATPlanningHelper({
  projectName,
  onContextReady,
  onPlanGenerated
}: UATPlanningHelperProps) {
  const { isUATMode } = useUATMode()
  const [stage, setStage] = useState<Stage>('gathering')
  const [expandedSection, setExpandedSection] = useState<string | null>(null)
  const [userMessage, setUserMessage] = useState<string | null>(null)
  const [feedbackText, setFeedbackText] = useState('')
  const [originalPlan, setOriginalPlan] = useState<GenerateTestPlanResponse | null>(null)

  // Only fetch context when in UAT mode
  const {
    data: context,
    isLoading: _isLoadingContext, // Prefix with underscore - used indirectly through context checks
    error: contextError,
  } = useUATProjectContext(isUATMode ? projectName : undefined)

  // Test plan generation mutation
  const generatePlan = useGenerateTestPlan()

  // Test plan modification mutation
  const modifyPlan = useModifyTestPlan()

  // Test plan approval mutation (Feature #11)
  const approvePlan = useApproveTestPlan()

  // Update stage when context is loaded
  useEffect(() => {
    if (context && isContextComplete(context)) {
      setStage('ready')
      onContextReady?.(context)
    }
  }, [context, onContextReady])

  // Don't render anything if not in UAT mode
  if (!isUATMode) {
    return null
  }

  // Context gathering stage
  if (stage === 'gathering') {
    return (
      <div className="border-2 border-[var(--color-neo-border)] bg-[var(--color-neo-bg)] p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Loader2 size={18} className="text-[var(--color-neo-progress)] animate-spin" />
          <h3 className="font-display font-bold text-[var(--color-neo-text)]">
            Gathering Project Context
          </h3>
        </div>

        <div className="space-y-2 text-sm">
          <ContextItem
            label="Reading app_spec.txt"
            status={context?.has_spec ? 'complete' : 'loading'}
          />
          <ContextItem
            label="Querying completed features"
            status={context ? (context.completed_features_count > 0 ? 'complete' : 'error') : 'loading'}
            count={context?.completed_features_count}
          />
          <ContextItem
            label="Loading UAT cycle history"
            status={context ? 'complete' : 'loading'}
          />
        </div>

        {contextError && (
          <div className="mt-3 p-2 bg-[var(--color-neo-danger)] bg-opacity-10 border border-[var(--color-neo-danger)] rounded">
            <div className="flex items-center gap-2 text-[var(--color-neo-danger)] text-sm">
              <AlertCircle size={14} />
              <span>{contextError.message}</span>
            </div>
          </div>
        )}

        {context && context.message && !context.success && (
          <div className="mt-3 p-2 bg-[var(--color-neo-warning)] bg-opacity-10 border border-[var(--color-neo-warning)] rounded">
            <div className="flex items-center gap-2 text-[var(--color-neo-warning)] text-sm">
              <AlertCircle size={14} />
              <span>{context.message}</span>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Ready to generate test plan stage
  if (stage === 'ready' && context) {
    const missing = getMissingContextItems(context)

    if (missing.length > 0) {
      return (
        <div className="border-2 border-[var(--color-neo-border)] bg-[var(--color-neo-bg)] p-4 mb-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertCircle size={18} className="text-[var(--color-neo-warning)]" />
            <h3 className="font-display font-bold text-[var(--color-neo-text)]">
              Incomplete Project Context
            </h3>
          </div>

          <p className="text-sm text-[var(--color-neo-text-secondary)] mb-3">
            The following items are needed before generating a UAT test plan:
          </p>

          <ul className="space-y-1 text-sm">
            {missing.map((item) => (
              <li key={item} className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 bg-[var(--color-neo-warning)] rounded-full" />
                <span className="text-[var(--color-neo-text)]">{item}</span>
              </li>
            ))}
          </ul>

          {!context.has_spec && (
            <p className="text-xs text-[var(--color-neo-text-secondary)] mt-3">
              Create an <code className="px-1 py-0.5 bg-[var(--color-neo-card)] rounded">app_spec.txt</code> file
              in your project directory to define your application requirements.
            </p>
          )}

          {context.completed_features_count === 0 && (
            <p className="text-xs text-[var(--color-neo-text-secondary)] mt-3">
              Complete at least one feature in Dev Mode before running UAT tests.
            </p>
          )}
        </div>
      )
    }

    return (
      <div className="border-2 border-[var(--color-neo-border)] bg-[var(--color-neo-bg)] p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle2 size={18} className="text-[var(--color-neo-done)]" />
          <h3 className="font-display font-bold text-[var(--color-neo-text)]">
            Ready to Generate Test Plan
          </h3>
        </div>

        <div className="space-y-3 text-sm mb-4">
          <div className="flex items-start gap-2">
            <FileText size={16} className="text-[var(--color-neo-done)] mt-0.5" />
            <div>
              <p className="font-medium text-[var(--color-neo-text)]">Project Specification</p>
              <p className="text-xs text-[var(--color-neo-text-secondary)]">
                {context.spec_content ? `${context.spec_content.length} bytes` : 'Not found'}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <List size={16} className="text-[var(--color-neo-done)] mt-0.5" />
            <div>
              <p className="font-medium text-[var(--color-neo-text)]">Completed Features</p>
              <p className="text-xs text-[var(--color-neo-text-secondary)]">
                {context.completed_features_count} features ready for testing
              </p>
            </div>
          </div>

          {context.uat_cycles_count > 0 && (
            <div className="flex items-start gap-2">
              <History size={16} className="text-[var(--color-neo-done)] mt-0.5" />
              <div>
                <p className="font-medium text-[var(--color-neo-text)]">Previous UAT Cycles</p>
                <p className="text-xs text-[var(--color-neo-text-secondary)]">
                  {context.uat_cycles_count} historical cycles found
                </p>
              </div>
            </div>
          )}
        </div>

        <button
          onClick={() => handleGeneratePlan()}
          disabled={generatePlan.isPending}
          className="
            w-full neo-btn neo-btn-primary
            flex items-center justify-center gap-2
            bg-[var(--color-neo-progress)] border-[var(--color-neo-border)]
            text-[var(--color-neo-text-on-bright)]
            disabled:opacity-50 disabled:cursor-not-allowed
          "
        >
          {generatePlan.isPending ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Generating Test Plan...
            </>
          ) : (
            <>
              <Sparkles size={16} />
              Generate UAT Test Plan
            </>
          )}
        </button>

        {generatePlan.error && (
          <div className="mt-3 p-2 bg-[var(--color-neo-danger)] bg-opacity-10 border border-[var(--color-neo-danger)] rounded">
            <div className="flex items-center gap-2 text-[var(--color-neo-danger)] text-sm">
              <AlertCircle size={14} />
              <span>{generatePlan.error.message}</span>
            </div>
          </div>
        )}

        {userMessage && (
          <div className="mt-3 p-2 bg-[var(--color-neo-info)] bg-opacity-10 border border-[var(--color-neo-info)] rounded">
            <div className="flex items-center gap-2 text-[var(--color-neo-info)] text-sm">
              <MessageSquare size={14} />
              <span>{userMessage}</span>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Generating test plan stage
  if (stage === 'generating') {
    return (
      <div className="border-2 border-[var(--color-neo-border)] bg-[var(--color-neo-bg)] p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Loader2 size={18} className="text-[var(--color-neo-progress)] animate-spin" />
          <h3 className="font-display font-bold text-[var(--color-neo-text)]">
            Analyzing Project & Generating Test Plan
          </h3>
        </div>

        <div className="space-y-2 text-sm">
          <ContextItem
            label="Parsing app_spec.txt"
            status="complete"
          />
          <ContextItem
            label="Identifying user journeys"
            status={generatePlan.isPending ? 'loading' : 'complete'}
          />
          <ContextItem
            label="Generating test scenarios"
            status={generatePlan.isPending ? 'loading' : 'complete'}
          />
          <ContextItem
            label="Creating test PRD"
            status={generatePlan.isPending ? 'loading' : 'complete'}
          />
        </div>
      </div>
    )
  }

  // Proposal stage - conversational interface
  if (stage === 'proposal' && generatePlan.data) {
    const plan = generatePlan.data

    return (
      <div className="border-2 border-[var(--color-neo-border)] bg-[var(--color-neo-bg)] p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles size={18} className="text-[var(--color-neo-progress)]" />
          <h3 className="font-display font-bold text-[var(--color-neo-text)]">
            Proposed UAT Test Plan
          </h3>
        </div>

        <p className="text-sm text-[var(--color-neo-text-secondary)] mb-4">
          I've analyzed your project and created a comprehensive test plan. Here's what I found:
        </p>

        {/* Summary */}
        <div className="bg-[var(--color-neo-card)] border border-[var(--color-neo-border)] p-3 mb-3">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-[var(--color-neo-text-secondary)]">Completed Features:</span>
              <span className="ml-2 font-medium text-[var(--color-neo-text)]">{plan.total_features_completed}</span>
            </div>
            <div>
              <span className="text-[var(--color-neo-text-secondary)]">Total Tests:</span>
              <span className="ml-2 font-medium text-[var(--color-neo-text)]">{plan.test_scenarios.length}</span>
            </div>
            <div>
              <span className="text-[var(--color-neo-text-secondary)]">Journeys:</span>
              <span className="ml-2 font-medium text-[var(--color-neo-text)]">{plan.journeys_identified.length}</span>
            </div>
            <div>
              <span className="text-[var(--color-neo-text-secondary)]">Phases:</span>
              <span className="ml-2 font-medium text-[var(--color-neo-text)]">{plan.recommended_phases.length}</span>
            </div>
          </div>
        </div>

        {/* Phases - Expandable */}
        <CollapsibleSection
          title="Test Phases"
          expanded={expandedSection === 'phases'}
          onToggle={() => setExpandedSection(expandedSection === 'phases' ? null : 'phases')}
        >
          <div className="space-y-2">
            {plan.recommended_phases.map((phase) => (
              <div
                key={phase.phase}
                className="flex items-start gap-2 p-2 bg-[var(--color-neo-card)] border border-[var(--color-neo-border)] rounded"
              >
                <div className="flex-1">
                  <p className="font-medium text-sm text-[var(--color-neo-text)]">{phase.phase}</p>
                  <p className="text-xs text-[var(--color-neo-text-secondary)]">{phase.description}</p>
                </div>
                <span className="text-xs font-mono bg-[var(--color-neo-bg)] px-2 py-1 rounded">
                  {phase.test_count} tests
                </span>
              </div>
            ))}
          </div>
        </CollapsibleSection>

        {/* Journeys - Expandable */}
        <CollapsibleSection
          title="User Journeys"
          expanded={expandedSection === 'journeys'}
          onToggle={() => setExpandedSection(expandedSection === 'journeys' ? null : 'journeys')}
        >
          <div className="space-y-2">
            {plan.journeys_identified.map((journey) => (
              <div
                key={journey.journey}
                className="flex items-start gap-2 p-2 bg-[var(--color-neo-card)] border border-[var(--color-neo-border)] rounded"
              >
                <div className="flex-1">
                  <p className="font-medium text-sm text-[var(--color-neo-text)] capitalize">{journey.journey}</p>
                  <p className="text-xs text-[var(--color-neo-text-secondary)]">
                    Phases: {journey.phases.join(', ')}
                  </p>
                </div>
                <span className="text-xs font-mono bg-[var(--color-neo-bg)] px-2 py-1 rounded">
                  {journey.test_count} tests
                </span>
              </div>
            ))}
          </div>
        </CollapsibleSection>

        {/* Test Scenarios - Expandable */}
        <CollapsibleSection
          title="Test Scenarios (Preview)"
          expanded={expandedSection === 'scenarios'}
          onToggle={() => setExpandedSection(expandedSection === 'scenarios' ? null : 'scenarios')}
        >
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {plan.test_scenarios.slice(0, 5).map((scenario) => (
              <div
                key={scenario.id}
                className="p-2 bg-[var(--color-neo-card)] border border-[var(--color-neo-border)] rounded"
              >
                <p className="text-xs font-medium text-[var(--color-neo-text)]">{scenario.scenario}</p>
                <p className="text-xs text-[var(--color-neo-text-secondary)] mt-1">
                  {scenario.phase} • {scenario.journey} • {scenario.test_type}
                </p>
              </div>
            ))}
            {plan.test_scenarios.length > 5 && (
              <p className="text-xs text-[var(--color-neo-text-secondary)] text-center">
                ... and {plan.test_scenarios.length - 5} more tests
              </p>
            )}
          </div>
        </CollapsibleSection>

        {/* Conversational Interaction */}
        <div className="mt-4 pt-4 border-t-2 border-[var(--color-neo-border)]">
          <p className="text-sm text-[var(--color-neo-text-secondary)] mb-3">
            What would you like to do with this test plan?
          </p>

          <div className="space-y-2">
            <button
              onClick={() => handleConfirmPlan()}
              disabled={approvePlan.isPending}
              className="
                w-full neo-btn neo-btn-primary
                flex items-center justify-center gap-2
                bg-[var(--color-neo-done)] border-[var(--color-neo-border)]
                text-[var(--color-neo-text-on-bright)]
                disabled:opacity-50 disabled:cursor-not-allowed
              "
            >
              {approvePlan.isPending ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Creating Tests...
                </>
              ) : (
                <>
                  <ThumbsUp size={16} />
                  Approve & Create Tests
                </>
              )}
            </button>

            <button
              onClick={() => handleRequestModification()}
              className="
                w-full neo-btn neo-btn-ghost
                flex items-center justify-center gap-2
                bg-[var(--color-neo-card)] border-[var(--color-neo-border)]
                text-[var(--color-neo-text)]
                hover:bg-[var(--color-neo-bg)]
              "
            >
              <MessageSquare size={16} />
              Request Changes
            </button>

            <button
              onClick={() => handleRejectPlan()}
              className="
                w-full neo-btn neo-btn-ghost
                flex items-center justify-center gap-2
                bg-[var(--color-neo-card)] border-[var(--color-neo-border)]
                text-[var(--color-neo-text)]
                hover:bg-[var(--color-neo-bg)]
              "
            >
              <ThumbsDown size={16} />
              Reject & Start Over
            </button>
          </div>

          {approvePlan.error && (
            <div className="mt-3 p-2 bg-[var(--color-neo-danger)] bg-opacity-10 border border-[var(--color-neo-danger)] rounded">
              <div className="flex items-center gap-2 text-[var(--color-neo-danger)] text-sm">
                <AlertCircle size={14} />
                <span>{approvePlan.error.message}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Confirming rejection stage - collect user feedback
  if (stage === 'confirming_rejection') {
    return (
      <div className="border-2 border-[var(--color-neo-warning)] bg-[var(--color-neo-bg)] p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <MessageSquare size={18} className="text-[var(--color-neo-warning)]" />
          <h3 className="font-display font-bold text-[var(--color-neo-text)]">
            Help Me Improve the Test Plan
          </h3>
        </div>

        <p className="text-sm text-[var(--color-neo-text-secondary)] mb-3">
          I want to create a better test plan for you. Can you tell me what didn't work with this proposal?
        </p>

        {/* Suggested feedback options */}
        <div className="mb-3 space-y-2">
          <p className="text-xs font-medium text-[var(--color-neo-text-secondary)]">
            Quick feedback options:
          </p>
          <div className="grid grid-cols-1 gap-2">
            <button
              onClick={() => setFeedbackText('Too many tests - I need a smaller test suite focused on critical paths only.')}
              className="text-left text-xs p-2 bg-[var(--color-neo-card)] border border-[var(--color-neo-border)] rounded hover:bg-[var(--color-neo-bg)] transition-colors"
            >
              "Too many tests - focus on critical paths only"
            </button>
            <button
              onClick={() => setFeedbackText('Missing tests for authentication and user management flows.')}
              className="text-left text-xs p-2 bg-[var(--color-neo-card)] border border-[var(--color-neo-border)] rounded hover:bg-[var(--color-neo-bg)] transition-colors"
            >
              "Missing tests for authentication and user management"
            </button>
            <button
              onClick={() => setFeedbackText('Skip regression tests - just do smoke and functional testing.')}
              className="text-left text-xs p-2 bg-[var(--color-neo-card)] border border-[var(--color-neo-border)] rounded hover:bg-[var(--color-neo-bg)] transition-colors"
            >
              "Skip regression tests - just smoke and functional"
            </button>
            <button
              onClick={() => setFeedbackText('Add more tests for payment and billing workflows.')}
              className="text-left text-xs p-2 bg-[var(--color-neo-card)] border border-[var(--color-neo-border)] rounded hover:bg-[var(--color-neo-bg)] transition-colors"
            >
              "Add more tests for payment and billing workflows"
            </button>
          </div>
        </div>

        {/* Custom feedback input */}
        <div className="mb-3">
          <label htmlFor="feedback-input" className="block text-xs font-medium text-[var(--color-neo-text-secondary)] mb-1">
            Or describe what you need in your own words:
          </label>
          <textarea
            id="feedback-input"
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            placeholder="E.g., 'Add 5 more tests for the admin dashboard' or 'Remove all mobile tests for now'"
            className="
              w-full p-2 text-sm
              bg-[var(--color-neo-card)]
              border border-[var(--color-neo-border)]
              rounded
              text-[var(--color-neo-text)]
              placeholder-[var(--color-neo-text-secondary)]
              focus:outline-none focus:ring-2 focus:ring-[var(--color-neo-progress)]
              resize-y
              min-h-[80px]
            "
          />
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          <button
            onClick={() => handleSubmitRejection()}
            disabled={!feedbackText.trim() || modifyPlan.isPending}
            className="
              flex-1 neo-btn neo-btn-primary
              flex items-center justify-center gap-2
              bg-[var(--color-neo-progress)] border-[var(--color-neo-border)]
              text-[var(--color-neo-text-on-bright)]
              disabled:opacity-50 disabled:cursor-not-allowed
            "
          >
            {modifyPlan.isPending ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Regenerating...
              </>
            ) : (
              <>
                <Send size={16} />
                Submit & Regenerate
              </>
            )}
          </button>

          <button
            onClick={() => handleCancelRejection()}
            className="
              flex-1 neo-btn neo-btn-ghost
              flex items-center justify-center gap-2
              bg-[var(--color-neo-card)] border-[var(--color-neo-border)]
              text-[var(--color-neo-text)]
              hover:bg-[var(--color-neo-bg)]
            "
          >
            Cancel
          </button>
        </div>

        {modifyPlan.error && (
          <div className="mt-3 p-2 bg-[var(--color-neo-danger)] bg-opacity-10 border border-[var(--color-neo-danger)] rounded">
            <div className="flex items-center gap-2 text-[var(--color-neo-danger)] text-sm">
              <AlertCircle size={14} />
              <span>{modifyPlan.error.message}</span>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Confirmed stage
  if (stage === 'confirmed') {
    return (
      <div className="border-2 border-[var(--color-neo-done)] bg-[var(--color-neo-bg)] p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle2 size={18} className="text-[var(--color-neo-done)]" />
          <h3 className="font-display font-bold text-[var(--color-neo-text)]">
            Test Plan Approved! 🎉
          </h3>
        </div>

        <p className="text-sm text-[var(--color-neo-text-secondary)] mb-3">
          Your UAT tests have been created and are now visible in the kanban board. You can start
          the test execution whenever you're ready.
        </p>

        <div className="text-xs text-[var(--color-neo-text-secondary)]">
          <p>Next steps:</p>
          <ul className="list-disc list-inside mt-1 space-y-1">
            <li>Review the test cards in the kanban board</li>
            <li>Start test execution when ready</li>
            <li>Monitor progress in real-time</li>
          </ul>
        </div>
      </div>
    )
  }

  return null

  // Handlers
  async function handleGeneratePlan() {
    if (!projectName) return

    setStage('generating')
    setUserMessage("I'm analyzing your project to create a comprehensive test plan...")

    try {
      const result = await generatePlan.mutateAsync({
        project_name: projectName,
      })

      setUserMessage(`I've created a test plan with ${result.test_scenarios.length} tests covering ${result.journeys_identified.length} user journeys.`)
      setStage('proposal')
      onPlanGenerated?.(result)
    } catch (error) {
      setUserMessage(null)
      setStage('ready')
    }
  }

  async function handleConfirmPlan() {
    if (!generatePlan.data?.cycle_id) {
      setUserMessage('Error: No test plan to approve')
      return
    }

    setUserMessage('Great! Creating your UAT tests in the database...')

    try {
      const result = await approvePlan.mutateAsync(generatePlan.data.cycle_id)

      // Show success message with test count
      setUserMessage(
        `✅ Success! Created ${result.tests_created} UAT tests in the database. ` +
        `Tests are now visible in the kanban board.`
      )

      // Move to confirmed stage
      setStage('confirmed')
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to create tests'
      setUserMessage(`❌ Error: ${errorMessage}`)
      // Don't change stage - let user try again
    }
  }

  function handleRequestModification() {
    setUserMessage('Sure! You can ask me to modify the plan. For example: "Add more tests for authentication" or "Skip the smoke tests"')
    // This will be handled by the conversational AI in future features
  }

  function handleRejectPlan() {
    // Save the original plan for reference
    if (generatePlan.data) {
      setOriginalPlan(generatePlan.data)
    }
    setFeedbackText('')
    setStage('confirming_rejection')
    setUserMessage('I\'d like to understand why this plan doesn\'t work for you. Can you tell me more?')
  }

  async function handleSubmitRejection() {
    if (!originalPlan || !feedbackText.trim()) {
      setUserMessage('Please provide some feedback so I can improve the plan.')
      return
    }

    setStage('generating')
    setUserMessage('Thanks for the feedback! Let me regenerate the plan based on your input...')

    try {
      // Determine modification type from user feedback (simple heuristic)
      let modificationType: 'add_tests' | 'remove_tests' | 'change_phases' | 'adjust_journeys' | 'custom' = 'custom'
      const feedbackLower = feedbackText.toLowerCase()

      if (feedbackLower.includes('remove') || feedbackLower.includes('skip') || feedbackLower.includes('don\'t need')) {
        modificationType = 'remove_tests'
      } else if (feedbackLower.includes('add') || feedbackLower.includes('more') || feedbackLower.includes('additional')) {
        modificationType = 'add_tests'
      } else if (feedbackLower.includes('phase') || feedbackLower.includes('smoke') || feedbackLower.includes('functional')) {
        modificationType = 'change_phases'
      } else if (feedbackLower.includes('journey') || feedbackLower.includes('scenario')) {
        modificationType = 'adjust_journeys'
      }

      const result = await modifyPlan.mutateAsync({
        project_name: originalPlan.project_name,
        cycle_id: originalPlan.cycle_id || '',
        modification_type: modificationType,
        user_message: feedbackText,
      })

      // Update the plan data with the modified version
      generatePlan.data = result as any

      setUserMessage(`I've updated the plan based on your feedback. ${result.message}`)
      setStage('proposal')
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to modify plan'
      setUserMessage(`Sorry, I couldn't modify the plan: ${errorMessage}`)
      setStage('proposal') // Go back to proposal stage so they can try again
    }
  }

  function handleCancelRejection() {
    setFeedbackText('')
    setOriginalPlan(null)
    setStage('proposal')
    setUserMessage('No problem! The original plan is still here for you to review.')
  }
}

interface ContextItemProps {
  label: string
  status: 'loading' | 'complete' | 'error'
  count?: number
}

function ContextItem({ label, status, count }: ContextItemProps) {
  return (
    <div className="flex items-center gap-2">
      {status === 'loading' && (
        <Loader2 size={14} className="text-[var(--color-neo-progress)] animate-spin" />
      )}
      {status === 'complete' && (
        <CheckCircle2 size={14} className="text-[var(--color-neo-done)]" />
      )}
      {status === 'error' && (
        <AlertCircle size={14} className="text-[var(--color-neo-danger)]" />
      )}

      <span className="text-[var(--color-neo-text-secondary)]">{label}</span>

      {count !== undefined && count > 0 && (
        <span className="text-xs text-[var(--color-neo-text)] ml-auto">
          {count} found
        </span>
      )}
    </div>
  )
}

interface CollapsibleSectionProps {
  title: string
  expanded: boolean
  onToggle: () => void
  children: React.ReactNode
}

function CollapsibleSection({ title, expanded, onToggle, children }: CollapsibleSectionProps) {
  return (
    <div className="mb-2">
      <button
        onClick={onToggle}
        className="
          w-full flex items-center justify-between
          p-2 bg-[var(--color-neo-card)]
          border border-[var(--color-neo-border)]
          text-left text-sm font-medium
          hover:bg-[var(--color-neo-bg)]
          transition-colors
        "
      >
        <span className="text-[var(--color-neo-text)]">{title}</span>
        {expanded ? (
          <ChevronUp size={16} className="text-[var(--color-neo-text-secondary)]" />
        ) : (
          <ChevronDown size={16} className="text-[var(--color-neo-text-secondary)]" />
        )}
      </button>

      {expanded && (
        <div className="mt-2 p-2 bg-[var(--color-neo-bg)] border border-[var(--color-neo-border)] rounded">
          {children}
        </div>
      )}
    </div>
  )
}
