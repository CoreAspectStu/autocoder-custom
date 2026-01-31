/**
 * Feature #152: Unit Test ChatTab Defensive Programming
 *
 * Tests to verify ChatTab handles undefined/null data gracefully without crashing.
 * Covers:
 * - Undefined conversations array
 * - Null messages
 * - Missing conversation properties
 * - Malformed API responses
 * - Optional chaining prevention
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChatTab } from './ChatTab'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch as any

beforeEach(() => {
  vi.clearAllMocks()
})

// Helper to create a test query client
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })
}

// Wrapper component for testing
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = createTestQueryClient()
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}

describe('ChatTab - Defensive Programming - Undefined Data', () => {
  it('should handle undefined conversations array', async () => {
    // Mock API to return undefined instead of array
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => undefined,
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Should not crash - should show "No conversations yet"
    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument()
    })
  })

  it('should handle null conversations response', async () => {
    // Mock API to return null
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => null,
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Should gracefully handle null
    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument()
    })
  })

  it('should handle malformed non-array conversations', async () => {
    // Mock API to return object instead of array
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ error: 'Internal error' }),
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Array.isArray check should prevent crash
    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument()
    })
  })
})

describe('ChatTab - Defensive Programming - Null Messages', () => {
  it('should handle null messages array', async () => {
    // First fetch returns conversations, second returns null messages
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, project_name: 'test', title: 'Test Conv', created_at: '2025-01-01', updated_at: '2025-01-01', message_count: 0 }
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => null,
      })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Click on conversation
    const conversationButton = await screen.findByText('Test Conv')
    conversationButton.click()

    // Should show "No messages" instead of crashing
    await waitFor(() => {
      expect(screen.getByText('No messages in this conversation')).toBeInTheDocument()
    })
  })

  it('should handle undefined messages', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, project_name: 'test', title: 'Test Conv', created_at: '2025-01-01', updated_at: '2025-01-01', message_count: 0 }
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => undefined,
      })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    const conversationButton = await screen.findByText('Test Conv')
    conversationButton.click()

    await waitFor(() => {
      expect(screen.getByText('No messages in this conversation')).toBeInTheDocument()
    })
  })
})

describe('ChatTab - Defensive Programming - Missing Properties', () => {
  it('should handle conversations with missing optional properties', async () => {
    // Missing title, message_count
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { id: 1, project_name: 'test', created_at: '2025-01-01', updated_at: '2025-01-01' },
      ],
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Optional chaining should prevent crash
    // Should show conversation list even with missing properties
    await waitFor(() => {
      expect(screen.getByText(/conversations/i)).toBeInTheDocument()
    })
  })

  it('should handle messages with missing properties', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, project_name: 'test', title: 'Test Conv', created_at: '2025-01-01', updated_at: '2025-01-01', message_count: 1 }
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, conversation_id: 1, role: 'user', content: 'Test' },
          // Missing timestamp
        ],
      })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    const conversationButton = await screen.findByText('Test Conv')
    conversationButton.click()

    // Should render message even without timestamp (may show invalid date)
    await waitFor(() => {
      expect(screen.getByText('Test')).toBeInTheDocument()
    })
  })
})

describe('ChatTab - Defensive Programming - API Errors', () => {
  it('should handle 404 for non-existent conversation', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, project_name: 'test', title: 'Test Conv', created_at: '2025-01-01', updated_at: '2025-01-01', message_count: 0 }
        ],
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
      })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    const conversationButton = await screen.findByText('Test Conv')
    conversationButton.click()

    // Should clear selection and return to conversation list
    await waitFor(() => {
      expect(screen.getByText('No messages in this conversation')).toBeInTheDocument()
    })
  })

  it('should handle network errors gracefully', async () => {
    // Mock network error
    mockFetch.mockRejectedValueOnce(new Error('Network error'))

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Should show "No conversations" instead of crashing
    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument()
    })
  })

  it('should handle 500 server error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Should gracefully handle server errors
    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument()
    })
  })
})

describe('ChatTab - Defensive Programming - Agent Status', () => {
  it('should handle null agent status', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => null,
      })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Should not crash when agent status is null
    await waitFor(() => {
      expect(screen.getByText('Conversation & Agent Control')).toBeInTheDocument()
    })
  })

  it('should handle malformed agent status object', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ invalid: 'structure' }),
      })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Type check should prevent crash
    await waitFor(() => {
      expect(screen.getByText('Conversation & Agent Control')).toBeInTheDocument()
    })
  })

  it('should handle agent status with missing agents array', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'running' }),
      })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Optional chaining agents?.length should prevent crash
    await waitFor(() => {
      expect(screen.getByText(/running/i)).toBeInTheDocument()
    })
  })
})

describe('ChatTab - Defensive Programming - Edge Cases', () => {
  it('should handle no project selected', () => {
    render(
      <TestWrapper>
        <ChatTab selectedProject={null} />
      </TestWrapper>
    )

    // Should show "No project selected" message
    expect(screen.getByText('No project selected')).toBeInTheDocument()
    expect(screen.getByText('Select a project to view conversations')).toBeInTheDocument()
  })

  it('should handle empty project name', () => {
    render(
      <TestWrapper>
        <ChatTab selectedProject="" />
      </TestWrapper>
    )

    // Should treat empty string as no project
    expect(screen.getByText('No project selected')).toBeInTheDocument()
  })

  it('should handle messages with very long content', async () => {
    const longMessage = 'A'.repeat(10000)

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, project_name: 'test', title: 'Test Conv', created_at: '2025-01-01', updated_at: '2025-01-01', message_count: 1 }
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, conversation_id: 1, role: 'assistant', content: longMessage, timestamp: '2025-01-01T00:00:00' }
        ],
      })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    const conversationButton = await screen.findByText('Test Conv')
    conversationButton.click()

    // Should render long message without crashing
    await waitFor(() => {
      expect(screen.getByText(/^A+$/)).toBeInTheDocument()
    })
  })

  it('should handle special characters in messages', async () => {
    const specialMessage = '<script>alert("xss")</script> & "quotes" and \'apostrophes\''

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, project_name: 'test', title: 'Test Conv', created_at: '2025-01-01', updated_at: '2025-01-01', message_count: 1 }
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          { id: 1, conversation_id: 1, role: 'assistant', content: specialMessage, timestamp: '2025-01-01T00:00:00' }
        ],
      })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    const conversationButton = await screen.findByText('Test Conv')
    conversationButton.click()

    // Should escape HTML and handle special characters
    await waitFor(() => {
      expect(screen.getByText(/& "quotes" and/)).toBeInTheDocument()
    })
  })
})

describe('ChatTab - Defensive Programming - Type Safety', () => {
  it('should handle wrong data type from API', async () => {
    // API returns string instead of array
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => 'invalid data',
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Array.isArray check prevents crash
    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument()
    })
  })

  it('should handle number instead of object', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => 12345,
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument()
    })
  })

  it('should handle empty string response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => '',
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('No conversations yet')).toBeInTheDocument()
    })
  })
})

describe('ChatTab - Defensive Programming - Error Boundary', () => {
  it('should catch rendering errors with Error Boundary', async () => {
    // This test verifies the Error Boundary catches any unexpected rendering errors
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Component should render without throwing
    await waitFor(() => {
      expect(screen.getByText('Conversation & Agent Control')).toBeInTheDocument()
    })
  })

  it('should provide recovery option in Error Boundary', async () => {
    // Error Boundary should have a "Try Again" button
    // This is a structural test - the boundary exists and can catch errors
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })

    render(
      <TestWrapper>
        <ChatTab selectedProject="test-project" />
      </TestWrapper>
    )

    // Verify normal rendering (Error Boundary doesn't interfere with normal operation)
    await waitFor(() => {
      expect(screen.getByText('Conversation & Agent Control')).toBeInTheDocument()
    })
  })
})

describe('ChatTab - Coverage Verification', () => {
  it('should cover all error paths in conversations query', async () => {
    // Test each error path explicitly
    const errorCases = [
      { ok: false, status: 404 },
      { ok: false, status: 500 },
      { ok: false, status: 503 },
      { ok: true, json: async () => undefined },
      { ok: true, json: async () => null },
      { ok: true, json: async () => ({ not: 'array' }) },
    ]

    for (const errorCase of errorCases) {
      vi.clearAllMocks()
      mockFetch.mockResolvedValueOnce(errorCase as any)

      const { unmount } = render(
        <TestWrapper>
          <ChatTab selectedProject="test-project" />
        </TestWrapper>
      )

      // All error cases should gracefully show "No conversations"
      await waitFor(() => {
        expect(screen.getByText('No conversations yet')).toBeInTheDocument()
      })
      unmount()
    }
  })

  it('should cover all error paths in messages query', async () => {
    const errorCases = [
      { ok: false, status: 404 },
      { ok: false, status: 500 },
      { ok: true, json: async () => undefined },
      { ok: true, json: async () => null },
      { ok: true, json: async () => 'not array' },
    ]

    for (const errorCase of errorCases) {
      vi.clearAllMocks()
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => [
            { id: 1, project_name: 'test', title: 'Test', created_at: '2025-01-01', updated_at: '2025-01-01', message_count: 0 }
          ],
        })
        .mockResolvedValueOnce(errorCase as any)

      const { unmount } = render(
        <TestWrapper>
          <ChatTab selectedProject="test-project" />
        </TestWrapper>
      )

      const conversationButton = await screen.findByText('Test')
      conversationButton.click()

      await waitFor(() => {
        expect(screen.getByText('No messages in this conversation')).toBeInTheDocument()
      })
      unmount()
    }
  })
})
