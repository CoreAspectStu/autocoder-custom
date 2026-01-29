/**
 * Hook for generating UAT test plans
 *
 * Calls the POST /api/uat/generate-plan endpoint to create
 * a proposed test framework based on project context.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'

export interface TestFrameworkProposal {
  phase: string
  description: string
  test_count: number
}

export interface JourneyProposal {
  journey: string
  test_count: number
  phases: string[]
}

export interface TestScenario {
  id: number
  phase: string
  journey: string
  scenario: string
  description: string
  test_type: string
  steps: string[]
  expected_result: string
  priority: number
  dependencies: number[]
}

export interface GenerateTestPlanResponse {
  success: boolean
  cycle_id: string | null
  project_name: string
  total_features_completed: number
  journeys_identified: JourneyProposal[]
  recommended_phases: TestFrameworkProposal[]
  test_scenarios: TestScenario[]
  test_dependencies: Record<number, number[]>
  test_prd: string
  message: string
  created_at: string | null
}

export interface GenerateTestPlanRequest {
  project_name: string
  project_path?: string
}

/**
 * Generate a UAT test plan for the given project
 *
 * @param projectName - Name of the project to generate a test plan for
 * @returns Mutation object with trigger function
 */
export function useGenerateTestPlan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (request: GenerateTestPlanRequest): Promise<GenerateTestPlanResponse> => {
      const response = await fetch('/api/uat/generate-plan', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({
          detail: 'Failed to generate test plan',
        }))
        throw new Error(error.detail || 'Failed to generate test plan')
      }

      return response.json()
    },
    onSuccess: (_data, variables) => {
      // Invalidate related queries to trigger refetch
      queryClient.invalidateQueries({
        queryKey: ['uat-project-context', variables.project_name],
      })
    },
  })
}
