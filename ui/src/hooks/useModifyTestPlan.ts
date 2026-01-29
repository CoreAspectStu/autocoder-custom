/**
 * Hook for modifying UAT test plans conversationally
 *
 * Calls the POST /api/uat/modify-plan endpoint to update
 * a proposed test framework based on user feedback.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'

export type ModificationType =
  | 'add_tests'
  | 'remove_tests'
  | 'change_phases'
  | 'adjust_journeys'
  | 'custom'

export interface ModifyTestPlanRequest {
  project_name: string
  cycle_id: string
  modification_type: ModificationType
  modification_params?: Record<string, any>
  user_message?: string
}

export interface ModifyTestPlanResponse {
  success: boolean
  cycle_id: string
  project_name: string
  original_test_count: number
  modified_test_count: number
  journeys_identified: Array<{
    journey: string
    test_count: number
    phases: string[]
  }>
  recommended_phases: Array<{
    phase: string
    description: string
    test_count: number
  }>
  test_scenarios: Array<{
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
  }>
  test_dependencies: Record<number, number[]>
  test_prd: string
  modifications_applied: string[]
  message: string
  created_at?: string
}

/**
 * Modify a UAT test plan based on user feedback
 *
 * @returns Mutation object with trigger function
 */
export function useModifyTestPlan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (request: ModifyTestPlanRequest): Promise<ModifyTestPlanResponse> => {
      const response = await fetch('/api/uat/modify-plan', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({
          detail: 'Failed to modify test plan',
        }))
        throw new Error(error.detail || 'Failed to modify test plan')
      }

      return response.json()
    },
    onSuccess: (data, variables) => {
      // Invalidate related queries to trigger refetch
      queryClient.invalidateQueries({
        queryKey: ['uat-project-context', variables.project_name],
      })
    },
  })
}
