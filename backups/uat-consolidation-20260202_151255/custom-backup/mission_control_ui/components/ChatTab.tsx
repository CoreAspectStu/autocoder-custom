import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Send,
  Loader2,
  Play,
  Pause,
  Square,
  MessageSquare,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle
} from 'lucide-react'

// Types for conversation history
interface ConversationMessage {
  id: number
  conversation_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
}

interface Conversation {
  id: number
  project_name: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

// Agent status types
interface AgentStatus {
  status: 'stopped' | 'running' | 'paused' | 'crashed'
  agents: Array<{
    index: number
    name: string
    type: 'coding' | 'testing'
    state: 'idle' | 'thinking' | 'working' | 'testing' | 'success' | 'error' | 'struggling'
    featureId: number | null
    featureName: string | null
    thought: string | null
  }>
}

// Mascot icons for agents
const AGENT_MASCOTS: Record<string, string> = {
  Spark: '⚡',
  Fizz: '🧪',
  Octo: '🐙',
  Hoot: '🦉',
  Buzz: '🐝'
}

interface ChatTabProps {
  selectedProject: string | null
}

export function ChatTab({ selectedProject }: ChatTabProps) {
  const [input, setInput] = useState('')
  const [selectedConversationId, setSelectedConversationId] = useState<number | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  // Fetch conversation list
  const { data: conversations = [], isLoading: conversationsLoading } = useQuery<Conversation[]>({
    queryKey: ['conversations', selectedProject],
    queryFn: async () => {
      if (!selectedProject) return []
      const res = await fetch(`/api/assistant/conversations/${encodeURIComponent(selectedProject)}`)
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!selectedProject,
    refetchInterval: 5000,
  })

  // Fetch messages for selected conversation
  const { data: messages = [], isLoading: messagesLoading } = useQuery<ConversationMessage[]>({
    queryKey: ['conversationMessages', selectedConversationId],
    queryFn: async () => {
      if (!selectedConversationId) return []
      const res = await fetch(`/api/assistant/conversations/${encodeURIComponent(selectedProject!)}/${selectedConversationId}`)
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!selectedConversationId,
    refetchInterval: 2000,
  })

  // Fetch agent status
  const { data: agentStatus } = useQuery<AgentStatus>({
    queryKey: ['agentStatus', selectedProject],
    queryFn: async () => {
      if (!selectedProject) return null
      const res = await fetch(`/api/projects/${encodeURIComponent(selectedProject)}/agent/status`)
      if (!res.ok) return null
      return res.json()
    },
    enabled: !!selectedProject,
    refetchInterval: 2000,
  })

  // WebSocket for real-time updates
  useEffect(() => {
    if (!selectedProject) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/projects/${encodeURIComponent(selectedProject)}`

    const ws = new WebSocket(wsUrl)

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        // Handle different message types
        if (data.type === 'agent_status' || data.type === 'agent_update') {
          // Refresh agent status
          queryClient.invalidateQueries({ queryKey: ['agentStatus', selectedProject] })
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    return () => ws.close()
  }, [selectedProject, queryClient])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Agent control mutations
  const startAgent = useMutation({
    mutationFn: async () => {
      if (!selectedProject) throw new Error('No project selected')
      const res = await fetch(`/api/projects/${encodeURIComponent(selectedProject)}/agent/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })
      if (!res.ok) throw new Error('Failed to start agent')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentStatus', selectedProject] })
    }
  })

  const stopAgent = useMutation({
    mutationFn: async () => {
      if (!selectedProject) throw new Error('No project selected')
      const res = await fetch(`/api/projects/${encodeURIComponent(selectedProject)}/agent/stop`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error('Failed to stop agent')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentStatus', selectedProject] })
    }
  })

  const pauseAgent = useMutation({
    mutationFn: async () => {
      if (!selectedProject) throw new Error('No project selected')
      const res = await fetch(`/api/projects/${encodeURIComponent(selectedProject)}/agent/pause`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error('Failed to pause agent')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentStatus', selectedProject] })
    }
  })

  const resumeAgent = useMutation({
    mutationFn: async () => {
      if (!selectedProject) throw new Error('No project selected')
      const res = await fetch(`/api/projects/${encodeURIComponent(selectedProject)}/agent/resume`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error('Failed to resume agent')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentStatus', selectedProject] })
    }
  })

  // Send message mutation
  const sendMessage = useMutation({
    mutationFn: async (content: string) => {
      if (!selectedProject) throw new Error('No project selected')

      // Create or use conversation
      const conversationId = selectedConversationId ||
        (await fetch(`/api/assistant/conversations/${encodeURIComponent(selectedProject)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: content.slice(0, 50) + (content.length > 50 ? '...' : '') })
        }).then(r => r.json())).id

      // Add message
      const res = await fetch(`/api/assistant/conversations/${encodeURIComponent(selectedProject)}/${conversationId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'user', content })
      })
      if (!res.ok) throw new Error('Failed to send message')
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversationMessages', selectedConversationId] })
      queryClient.invalidateQueries({ queryKey: ['conversations', selectedProject] })
      setInput('')
    }
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim() && !sendMessage.isPending) {
      sendMessage.mutate(input.trim())
    }
  }

  const getAgentStateIcon = (state: string) => {
    switch (state) {
      case 'thinking': return <Loader2 className="animate-spin text-blue-500" size={16} />
      case 'working': return <Loader2 className="animate-spin text-purple-500" size={16} />
      case 'testing': return <CheckCircle2 className="text-green-500" size={16} />
      case 'success': return <CheckCircle2 className="text-green-600" size={16} />
      case 'error': return <XCircle className="text-red-500" size={16} />
      case 'struggling': return <AlertCircle className="text-orange-500" size={16} />
      default: return <div className="w-4 h-4 rounded-full bg-gray-300" />
    }
  }

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp)
    const today = new Date()
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    if (date.toDateString() === today.toDateString()) return 'Today'
    if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  if (!selectedProject) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <MessageSquare size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-lg mb-2">No project selected</p>
          <p className="text-sm">Select a project to view conversations</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-gray-50 dark:bg-gray-900">
      {/* Header with Agent Control */}
      <div className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Conversation & Agent Control
            </h2>
            <p className="text-sm text-gray-500">{selectedProject}</p>
          </div>
        </div>

        {/* Agent Control Panel */}
        {agentStatus && (
          <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${
                  agentStatus.status === 'running' ? 'bg-green-500 animate-pulse' :
                  agentStatus.status === 'paused' ? 'bg-yellow-500' :
                  agentStatus.status === 'crashed' ? 'bg-red-500' :
                  'bg-gray-400'
                }`} />
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300 capitalize">
                  {agentStatus.status}
                </span>
                {agentStatus.agents && agentStatus.agents.length > 0 && (
                  <span className="text-xs text-gray-500">
                    ({agentStatus.agents.length} agent{agentStatus.agents.length > 1 ? 's' : ''})
                  </span>
                )}
              </div>

              {/* Agent Control Buttons */}
              <div className="flex gap-2">
                {agentStatus.status === 'running' && (
                  <>
                    <button
                      onClick={() => pauseAgent.mutate()}
                      disabled={pauseAgent.isPending}
                      className="px-3 py-1.5 bg-yellow-500 hover:bg-yellow-600 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 disabled:opacity-50"
                      title="Pause agent"
                    >
                      <Pause size={14} />
                      Pause
                    </button>
                    <button
                      onClick={() => stopAgent.mutate()}
                      disabled={stopAgent.isPending}
                      className="px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 disabled:opacity-50"
                      title="Stop agent immediately"
                    >
                      <Square size={14} />
                      Stop
                    </button>
                  </>
                )}
                {agentStatus.status === 'paused' && (
                  <>
                    <button
                      onClick={() => resumeAgent.mutate()}
                      disabled={resumeAgent.isPending}
                      className="px-3 py-1.5 bg-green-500 hover:bg-green-600 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 disabled:opacity-50"
                      title="Resume agent"
                    >
                      <Play size={14} />
                      Resume
                    </button>
                    <button
                      onClick={() => stopAgent.mutate()}
                      disabled={stopAgent.isPending}
                      className="px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 disabled:opacity-50"
                      title="Stop agent"
                    >
                      <Square size={14} />
                      Stop
                    </button>
                  </>
                )}
                {(agentStatus.status === 'stopped' || agentStatus.status === 'crashed') && (
                  <button
                    onClick={() => startAgent.mutate()}
                    disabled={startAgent.isPending}
                    className="px-3 py-1.5 bg-green-500 hover:bg-green-600 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 disabled:opacity-50"
                    title="Start agent"
                  >
                    <Play size={14} />
                    Start Agent
                  </button>
                )}
              </div>
            </div>

            {/* Active Agents Display */}
            {agentStatus.agents && agentStatus.agents.length > 0 && (
              <div className="space-y-2 max-h-32 overflow-y-auto">
                {agentStatus.agents.map((agent) => (
                  <div key={`${agent.index}-${agent.type}`} className="flex items-center gap-3 text-xs bg-white dark:bg-gray-800 rounded px-2 py-1.5">
                    <span className="text-lg">{AGENT_MASCOTS[agent.name] || '🤖'}</span>
                    <span className="font-medium text-gray-700 dark:text-gray-300">{agent.name}</span>
                    <span className="text-gray-500">•</span>
                    <span className="text-gray-600 dark:text-gray-400 capitalize">{agent.type}</span>
                    <span className="text-gray-500">•</span>
                    {getAgentStateIcon(agent.state)}
                    {agent.thought && (
                      <span className="flex-1 truncate text-gray-600 dark:text-gray-400" title={agent.thought}>
                        {agent.thought}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Conversations Sidebar */}
        <div className="w-80 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-y-auto">
          <div className="p-3 border-b border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
              <MessageSquare size={16} />
              Conversations ({conversations.length})
            </h3>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-gray-700">
            {conversationsLoading ? (
              <div className="p-4 text-center">
                <Loader2 className="animate-spin mx-auto text-gray-400" size={24} />
              </div>
            ) : conversations.length === 0 ? (
              <div className="p-4 text-center text-sm text-gray-500">
                No conversations yet
              </div>
            ) : (
              conversations.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => setSelectedConversationId(conv.id)}
                  className={`w-full text-left p-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
                    selectedConversationId === conv.id ? 'bg-purple-50 dark:bg-purple-900/20 border-l-2 border-purple-500' : ''
                  }`}
                >
                  <div className="flex items-start justify-between mb-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2 flex-1">
                      {conv.title}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <Clock size={12} />
                    <span>{formatDate(conv.updated_at)}</span>
                    <span>•</span>
                    <span>{conv.message_count} messages</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Messages Area */}
        <div className="flex-1 flex flex-col">
          {/* Messages List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messagesLoading && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="animate-spin text-gray-400" size={32} />
              </div>
            )}

            {!messagesLoading && messages.length === 0 && (
              <div className="text-center text-gray-500 py-8">
                <MessageSquare size={48} className="mx-auto mb-4 opacity-50" />
                <p className="text-lg mb-2">No messages in this conversation</p>
                <p className="text-sm">Select a conversation or start a new one below</p>
              </div>
            )}

            {!messagesLoading && messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-2 ${
                    msg.role === 'user'
                      ? 'bg-purple-500 text-white'
                      : msg.role === 'system'
                      ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200 border border-yellow-300 dark:border-yellow-700'
                      : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700'
                  }`}
                >
                  <div className="flex items-baseline gap-2 mb-1">
                    <span className={`text-xs font-medium ${
                      msg.role === 'user'
                        ? 'text-purple-200'
                        : msg.role === 'system'
                        ? 'text-yellow-700 dark:text-yellow-300'
                        : 'text-purple-600 dark:text-purple-400'
                    }`}>
                      {msg.role === 'user' ? 'You' : msg.role === 'system' ? 'System' : 'Assistant'}
                    </span>
                    <span className={`text-xs ${
                      msg.role === 'user' ? 'text-purple-200' : 'text-gray-500'
                    }`}>
                      {formatTime(msg.timestamp)}
                    </span>
                  </div>
                  <p className={`text-sm whitespace-pre-wrap ${
                    msg.role === 'user' || msg.role === 'system'
                      ? ''
                      : 'text-gray-900 dark:text-gray-100'
                  }`}>
                    {msg.content}
                  </p>
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
                placeholder="Type a message to the assistant..."
                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                disabled={sendMessage.isPending}
              />
              <button
                type="submit"
                disabled={!input.trim() || sendMessage.isPending}
                className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
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
      </div>
    </div>
  )
}
