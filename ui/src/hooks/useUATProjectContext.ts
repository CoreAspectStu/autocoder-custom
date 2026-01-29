/**
 * Hook for gathering UAT project context
 *
 * Fetches project context for UAT test planning:
 * - app_spec.txt content
 * - Completed features from features.db
 * - Previous UAT cycle history from uat_tests.db
 */

import { useQuery } from '@tanstack/react-query'

interface UATFeature {
  id: number
  priority: number
  category: string
  name: string
  description: string
  completed_at: string | null
}

interface UATCycle {
  id: number
  name: string
  phase: string
  journey: string
  status: string
  result: string
}

export interface UATProjectContext {
  success: boolean
  project_name: string
  has_spec: boolean
  spec_content: string | null
  completed_features_count: number
  completed_features: UATFeature[]
  uat_cycles_count: number
  uat_cycles: UATCycle[]
  message: string
}

/**
 * Fetch UAT project context for a given project
 *
 * @param projectName - Name of the project to gather context for
 * @returns Query result with project context data
 */
export function useUATProjectContext(projectName: string | undefined) {
  return useQuery({
    queryKey: ['uat-project-context', projectName],
    queryFn: async () => {
      if (!projectName) {
        throw new Error('Project name is required')
      }

      const response = await fetch(
        `/api/uat/context/${encodeURIComponent(projectName)}`
      )

      if (!response.ok) {
        const error = await response.json().catch(() => ({
          detail: 'Failed to fetch project context'
        }))
        throw new Error(error.detail || 'Failed to fetch project context')
      }

      return response.json() as Promise<UATProjectContext>
    },
    enabled: !!projectName,
    staleTime: 5 * 60 * 1000, // 5 minutes - context doesn't change often
    gcTime: 10 * 60 * 1000, // 10 minutes (renamed from cacheTime in React Query v5)
  })
}

/**
 * Check if project context is complete (has spec and completed features)
 *
 * @param context - Project context to check
 * @returns true if context is complete enough for UAT planning
 */
export function isContextComplete(context: UATProjectContext | undefined): boolean {
  if (!context) return false
  return context.has_spec && context.completed_features_count > 0
}

/**
 * Get missing context items
 *
 * @param context - Project context to check
 * @returns Array of missing context item names
 */
export function getMissingContextItems(
  context: UATProjectContext | undefined
): string[] {
  if (!context) return ['project context']

  const missing: string[] = []
  if (!context.has_spec) missing.push('app_spec.txt')
  if (context.completed_features_count === 0) missing.push('completed features')

  return missing
}
