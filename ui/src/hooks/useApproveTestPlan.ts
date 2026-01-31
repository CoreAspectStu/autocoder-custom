/**
 * Hook for approving UAT test plans
 *
 * Calls the POST /api/uat/approve-plan/{cycle_id} endpoint to
 * create UAT test tasks in the database from a proposed test plan.
 *
 * Feature #11: User can confirm test framework
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'

export interface ApproveTestPlanResponse {
  success: boolean
  cycle_id: string
  project_name: string
  tests_created: number
  test_ids: number[]
  message: string
  approved_at: string | null
}

export interface ApproveTestPlanRequest {
  cycle_id: string
}

/**
 * Approve a UAT test plan and create test tasks in database
 *
 * @param cycleId - Unique cycle identifier from test plan generation
 * @returns Mutation object with trigger function
 */
export function useApproveTestPlan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (cycleId: string): Promise<ApproveTestPlanResponse> => {
      const response = await fetch(`/api/uat/approve-plan/${cycleId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({
          detail: 'Failed to approve test plan',
        }))
        throw new Error(error.detail || 'Failed to approve test plan')
      }

      return response.json()
    },
    onSuccess: (data) => {
      // Invalidate UAT tests query to trigger refetch of newly created tests
      queryClient.invalidateQueries({
        queryKey: ['uat-tests'],
      })

      // Invalidate project context to update counts
      queryClient.invalidateQueries({
        queryKey: ['uat-project-context'],
      })
    },
  })
}
