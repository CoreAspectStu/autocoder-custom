/**
 * React Query hooks for UAT test data
 *
 * These hooks mirror the feature hooks but query from uat_tests.db
 * instead of features.db when UAT mode is active.
 */

import { useQuery } from '@tanstack/react-query'
import * as api from '../lib/api'

// ============================================================================
// UAT Tests
// ============================================================================

/**
 * Fetch UAT tests from uat_tests.db
 * Used when UAT mode is active
 */
export function useUATTests() {
  return useQuery({
    queryKey: ['uat-tests'],
    queryFn: api.listUATTests,
    refetchInterval: 5000, // Refetch every 5 seconds for real-time updates
    staleTime: 2000, // Consider data fresh for 2 seconds
  })
}

/**
 * Get UAT statistics summary
 * Returns total, passing, in-progress counts and percentage
 */
export function useUATStats() {
  return useQuery({
    queryKey: ['uat-stats'],
    queryFn: api.getUATStatsSummary,
    refetchInterval: 10000, // Refetch every 10 seconds
    staleTime: 5000,
  })
}

/**
 * Get a specific UAT test by ID
 */
export function useUATTest(testId: number) {
  return useQuery({
    queryKey: ['uat-test', testId],
    queryFn: () => api.getUATTest(testId),
    enabled: !!testId,
  })
}
