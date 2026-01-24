import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Send, Loader2 } from 'lucide-react'

interface ChatMessage {
  id: string
  project: string
  role: 'human' | 'agent'
  content: string
  created_at: string
}

interface ChatTabProps {
  selectedProject: string | null
}

export function ChatTab({ selectedProject }: ChatTabProps) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  // Fetch chat messages for selected project
  const { data: messages = [], isLoading } = useQuery<ChatMessage[]>({
    queryKey: ['devlayer', 'chat', selectedProject],
    queryFn: async () => {
      if (!selectedProject) return []
      const res = await fetch(`/api/devlayer/projects/${encodeURIComponent(selectedProject)}/chat?limit=1000`)
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!selectedProject,
    refetchInterval: 3000, // Poll every 3 seconds for new messages
  })

  // Send message mutation
  const sendMessage = useMutation({
    mutationFn: async (content: string) => {
      if (!selectedProject) throw new Error('No project selected')
      const res = await fetch(`/api/devlayer/projects/${encodeURIComponent(selectedProject)}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      })
      if (!res.ok) throw new Error('Failed to send message')
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devlayer', 'chat', selectedProject] })
      setInput('')
    }
  })

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim() && !sendMessage.isPending) {
      sendMessage.mutate(input.trim())
    }
  }

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    })
  }

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp)
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    if (date.toDateString() === today.toDateString()) {
      return 'Today'
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Yesterday'
    } else {
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined
      })
    }
  }

  // Group messages by date
  const groupedMessages = messages.reduce((groups, msg) => {
    const date = formatDate(msg.created_at)
    if (!groups[date]) groups[date] = []
    groups[date].push(msg)
    return groups
  }, {} as Record<string, ChatMessage[]>)

  if (!selectedProject) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <p className="text-lg mb-2">No project selected</p>
          <p className="text-sm">Select a project to view chat history</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-gray-50 dark:bg-gray-900">
      {/* Chat Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="animate-spin text-gray-400" size={32} />
          </div>
        )}

        {!isLoading && messages.length === 0 && (
          <div className="text-center text-gray-500 py-8">
            <p className="text-lg mb-2">No messages yet</p>
            <p className="text-sm">Start a conversation with the agent below</p>
          </div>
        )}

        {!isLoading && Object.entries(groupedMessages).map(([date, msgs]) => (
          <div key={date}>
            {/* Date Separator */}
            <div className="flex items-center justify-center mb-4">
              <div className="px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded-full text-xs font-medium text-gray-600 dark:text-gray-400">
                {date}
              </div>
            </div>

            {/* Messages for this date */}
            <div className="space-y-3">
              {msgs.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === 'human' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[70%] rounded-lg px-4 py-2 ${
                      msg.role === 'human'
                        ? 'bg-purple-500 text-white'
                        : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700'
                    }`}
                  >
                    <div className="flex items-baseline gap-2 mb-1">
                      <span className={`text-xs font-medium ${
                        msg.role === 'human'
                          ? 'text-purple-200'
                          : 'text-purple-600 dark:text-purple-400'
                      }`}>
                        {msg.role === 'human' ? 'You' : 'Agent'}
                      </span>
                      <span className={`text-xs ${
                        msg.role === 'human'
                          ? 'text-purple-200'
                          : 'text-gray-500 dark:text-gray-400'
                      }`}>
                        {formatTime(msg.created_at)}
                      </span>
                    </div>
                    <p className={`text-sm whitespace-pre-wrap ${
                      msg.role === 'human'
                        ? 'text-white'
                        : 'text-gray-900 dark:text-gray-100'
                    }`}>
                      {msg.content}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Box */}
      <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message to the agent..."
            className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
            disabled={sendMessage.isPending}
          />
          <button
            type="submit"
            disabled={!input.trim() || sendMessage.isPending}
            className="neo-btn px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {sendMessage.isPending ? (
              <Loader2 className="animate-spin" size={18} />
            ) : (
              <Send size={18} />
            )}
            Send
          </button>
        </form>
      </div>
    </div>
  )
}
