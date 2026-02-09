/**
 * React Query hooks for assistant conversation management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../lib/api'

/**
 * List all conversations for a project
 */
export function useConversations(projectName: string | null, mode: 'dev' | 'uat' = 'dev') {
  return useQuery({
    queryKey: ['conversations', projectName, mode],
    queryFn: () => api.listAssistantConversations(projectName!, mode),
    enabled: !!projectName,
    staleTime: 30000, // Cache for 30 seconds
  })
}

/**
 * Get a single conversation with all its messages
 */
export function useConversation(projectName: string | null, conversationId: number | null, mode: 'dev' | 'uat' = 'dev') {
  return useQuery({
    queryKey: ['conversation', projectName, conversationId, mode],
    queryFn: () => api.getAssistantConversation(projectName!, conversationId!, mode),
    enabled: !!projectName && !!conversationId,
    staleTime: 30_000, // Cache for 30 seconds
    retry: (failureCount, error) => {
      // Don't retry on "not found" errors (404) - conversation doesn't exist
      if (error instanceof Error && (
        error.message.toLowerCase().includes('not found') ||
        error.message === 'HTTP 404'
      )) {
        return false
      }
      return failureCount < 3
    },
  })
}

/**
 * Delete a conversation
 */
export function useDeleteConversation(projectName: string, mode: 'dev' | 'uat' = 'dev') {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (conversationId: number) =>
      api.deleteAssistantConversation(projectName, conversationId, mode),
    onSuccess: (_, deletedId) => {
      // Invalidate conversations list
      queryClient.invalidateQueries({ queryKey: ['conversations', projectName, mode] })
      // Remove the specific conversation from cache
      queryClient.removeQueries({ queryKey: ['conversation', projectName, deletedId, mode] })
    },
  })
}
