import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatTab } from '../ChatTab'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch as any

// Helper function to render component with providers
function renderChatTab(selectedProject: string | null = 'test-project') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchInterval: false,
      },
    },
  })

  return {
    ...render(
      <QueryClientProvider client={queryClient}>
        <ChatTab selectedProject={selectedProject} />
      </QueryClientProvider>
    ),
    queryClient,
  }
}

describe('ChatTab - 404 Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Suppress console errors in tests unless we're testing for them
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Conversation 404 Handling', () => {
    it('should clear selectedConversationId when conversation detail returns 404', async () => {
      // Mock conversation list success
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            id: 1,
            project_name: 'test-project',
            title: 'Test Conversation',
            created_at: '2024-01-01T00:00:00',
            updated_at: '2024-01-01T00:00:00',
            message_count: 5,
          },
        ],
      })

      // Mock conversation detail 404
      mockFetch.mockResolvedValueOnce({
        status: 404,
        ok: false,
        json: async () => ({ error: 'Not found' }),
      })

      const { queryClient } = renderChatTab()

      // Wait for conversations to load
      await waitFor(() => {
        expect(screen.getByText(/Test Conversation/)).toBeInTheDocument()
      })

      // Click on the conversation
      const conversationButton = screen.getByText(/Test Conversation/)
      fireEvent.click(conversationButton)

      // The 404 response should trigger setSelectedConversationId(null)
      // which will be reflected in the UI by deselecting the conversation
      await waitFor(
        () => {
          // Verify console.warn was called with 404 message
          expect(console.warn).toHaveBeenCalledWith(
            expect.stringContaining('Conversation 1 not found')
          )
        },
        { timeout: 3000 }
      )

      // Verify that after 404, the conversation is no longer selected
      // (the button should not have the selected styling)
      await waitFor(() => {
        const button = screen.getByText(/Test Conversation/)
        expect(button).not.toHaveClass('border-l-2')
      })
    })

    it('should render without crashing after 404 error', async () => {
      // Mock conversation list
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            id: 2,
            project_name: 'test-project',
            title: 'Another Conversation',
            created_at: '2024-01-01T00:00:00',
            updated_at: '2024-01-01T00:00:00',
            message_count: 3,
          },
        ],
      })

      // Mock 404 for conversation detail
      mockFetch.mockResolvedValueOnce({
        status: 404,
        ok: false,
      })

      const { container } = renderChatTab()

      // Wait for initial render
      await waitFor(() => {
        expect(screen.getByText(/Another Conversation/)).toBeInTheDocument()
      })

      // Component should still be in the document (no crash)
      expect(container.firstChild).toBeInTheDocument()

      // Click on conversation to trigger 404
      fireEvent.click(screen.getByText(/Another Conversation/))

      // Wait for 404 handling
      await waitFor(
        () => {
          expect(console.warn).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )

      // Component should still be rendered after 404
      expect(container.firstChild).toBeInTheDocument()
    })

    it('should display empty state message after 404 clears conversation', async () => {
      // Mock conversation list
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            id: 3,
            project_name: 'test-project',
            title: 'Vanishing Conversation',
            created_at: '2024-01-01T00:00:00',
            updated_at: '2024-01-01T00:00:00',
            message_count: 1,
          },
        ],
      })

      // Mock 404 for messages
      mockFetch.mockResolvedValueOnce({
        status: 404,
        ok: false,
      })

      renderChatTab()

      // Wait for conversations to load
      await waitFor(() => {
        expect(screen.getByText(/Vanishing Conversation/)).toBeInTheDocument()
      })

      // Click to trigger 404
      fireEvent.click(screen.getByText(/Vanishing Conversation/))

      // After 404 is handled, the conversation should be deselected
      // and we should see the "No messages in this conversation" message
      await waitFor(
        () => {
          expect(screen.getByText(/No messages in this conversation/)).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('should verify no console errors occur during 404 handling', async () => {
      // Track console.error calls
      const errorSpy = vi.spyOn(console, 'error')

      // Mock conversation list
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            id: 4,
            project_name: 'test-project',
            title: 'Error Test Conversation',
            created_at: '2024-01-01T00:00:00',
            updated_at: '2024-01-01T00:00:00',
            message_count: 0,
          },
        ],
      })

      // Mock 404 for conversation detail
      mockFetch.mockResolvedValueOnce({
        status: 404,
        ok: false,
      })

      renderChatTab()

      // Wait and click
      await waitFor(() => {
        expect(screen.getByText(/Error Test Conversation/)).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText(/Error Test Conversation/))

      // Wait for 404 handling
      await waitFor(
        () => {
          expect(console.warn).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )

      // Console.error should NOT have been called with an actual error
      // (only console.warn should be used for the 404)
      const errorCalls = errorSpy.mock.calls.filter((call) => {
        return call[0] && !call[0].includes('Failed to fetch messages')
      })
      expect(errorCalls.length).toBe(0)

      errorSpy.mockRestore()
    })
  })

  describe('Multiple 404 Scenarios', () => {
    it('should handle multiple consecutive 404 errors gracefully', async () => {
      // Mock conversation list with multiple conversations
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => [
          {
            id: 5,
            project_name: 'test-project',
            title: 'First Conversation',
            created_at: '2024-01-01T00:00:00',
            updated_at: '2024-01-01T00:00:00',
            message_count: 2,
          },
          {
            id: 6,
            project_name: 'test-project',
            title: 'Second Conversation',
            created_at: '2024-01-01T00:00:00',
            updated_at: '2024-01-01T00:00:00',
            message_count: 3,
          },
        ],
      })

      renderChatTab()

      // Wait for conversations
      await waitFor(() => {
        expect(screen.getByText(/First Conversation/)).toBeInTheDocument()
        expect(screen.getByText(/Second Conversation/)).toBeInTheDocument()
      })

      // Click first conversation - should get 404
      fireEvent.click(screen.getByText(/First Conversation/))

      await waitFor(
        () => {
          expect(console.warn).toHaveBeenCalledWith(
            expect.stringContaining('Conversation 5 not found')
          )
        },
        { timeout: 3000 }
      )

      // Click second conversation - should also get 404
      fireEvent.click(screen.getByText(/Second Conversation/))

      await waitFor(
        () => {
          expect(console.warn).toHaveBeenCalledWith(
            expect.stringContaining('Conversation 6 not found')
          )
        },
        { timeout: 3000 }
      )

      // Component should still be functional
      expect(screen.getByText(/First Conversation/)).toBeInTheDocument()
      expect(screen.getByText(/Second Conversation/)).toBeInTheDocument()
    })
  })

  describe('Error Recovery', () => {
    it('should allow retrying conversation selection after 404', async () => {
      let callCount = 0

      // Mock conversation list
      mockFetch.mockImplementation((url: string) => {
        if (url.includes('/conversations/test-project')) {
          return Promise.resolve({
            ok: true,
            json: async () => [
              {
                id: 7,
                project_name: 'test-project',
                title: 'Retry Conversation',
                created_at: '2024-01-01T00:00:00',
                updated_at: '2024-01-01T00:00:00',
                message_count: 1,
              },
            ],
          })
        } else if (url.includes('/conversations/test-project/7')) {
          callCount++
          // First call: 404, second call: success
          if (callCount === 1) {
            return Promise.resolve({
              status: 404,
              ok: false,
            })
          } else {
            return Promise.resolve({
              ok: true,
              json: async () => [
                {
                  id: 1,
                  conversation_id: 7,
                  role: 'assistant',
                  content: 'Hello!',
                  timestamp: '2024-01-01T00:00:00',
                },
              ],
            })
          }
        }
        return Promise.resolve({ ok: false, status: 404 })
      })

      const { queryClient } = renderChatTab()

      // Wait for conversations
      await waitFor(() => {
        expect(screen.getByText(/Retry Conversation/)).toBeInTheDocument()
      })

      // First click - 404
      fireEvent.click(screen.getByText(/Retry Conversation/))

      await waitFor(
        () => {
          expect(console.warn).toHaveBeenCalled()
        },
        { timeout: 3000 }
      )

      // Second click - success
      fireEvent.click(screen.getByText(/Retry Conversation/))

      // Should eventually load messages
      await waitFor(
        () => {
          expect(screen.getByText(/Hello!/)).toBeInTheDocument()
        },
        { timeout: 5000 }
      )
    })
  })

  describe('Edge Cases', () => {
    it('should handle 404 when selectedConversationId is already null', async () => {
      // Mock empty conversation list
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => [],
      })

      const { container } = renderChatTab()

      // Should render without crashing
      await waitFor(() => {
        expect(screen.getByText(/No conversations yet/)).toBeInTheDocument()
      })

      expect(container.firstChild).toBeInTheDocument()
    })

    it('should handle 404 for non-existent conversation ID', async () => {
      // Mock conversation list
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            id: 8,
            project_name: 'test-project',
            title: 'Real Conversation',
            created_at: '2024-01-01T00:00:00',
            updated_at: '2024-01-01T00:00:00',
            message_count: 1,
          },
        ],
      })

      // Mock 404 for very high conversation ID (doesn't exist)
      mockFetch.mockResolvedValueOnce({
        status: 404,
        ok: false,
        json: async () => ({ error: 'Conversation not found' }),
      })

      renderChatTab()

      await waitFor(() => {
        expect(screen.getByText(/Real Conversation/)).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText(/Real Conversation/))

      // Should handle gracefully
      await waitFor(
        () => {
          expect(console.warn).toHaveBeenCalledWith(
            expect.stringContaining('not found')
          )
        },
        { timeout: 3000 }
      )

      // No crash, component still rendered
      expect(screen.getByText(/Real Conversation/)).toBeInTheDocument()
    })
  })
})

describe('ChatTab - Basic Rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should render "No project selected" when no project is provided', () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [],
    })

    const { container } = renderChatTab(null)

    expect(screen.getByText(/No project selected/)).toBeInTheDocument()
    expect(screen.getByText(/Select a project to view conversations/)).toBeInTheDocument()
    expect(container.firstChild).toBeInTheDocument()
  })

  it('should render conversation list when project is selected', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [
        {
          id: 9,
          project_name: 'test-project',
          title: 'My Conversation',
          created_at: '2024-01-01T00:00:00',
          updated_at: '2024-01-01T00:00:00',
          message_count: 5,
        },
      ],
    })

    renderChatTab('my-project')

    await waitFor(() => {
      expect(screen.getByText(/My Conversation/)).toBeInTheDocument()
    })

    expect(screen.getByText(/Conversations \(1\)/)).toBeInTheDocument()
  })
})
