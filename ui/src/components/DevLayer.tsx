import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Bug, Lightbulb, StickyNote, Send, ChevronDown, ChevronRight, BellOff, Bell } from 'lucide-react'

interface Project {
  name: string
  path: string
  created_at?: string
}

interface AgentRequest {
  id: string
  project: string
  type: 'question' | 'auth_needed' | 'blocker' | 'decision'
  priority: 'critical' | 'normal' | 'low'
  message: string
  context?: string
  created_at: string
  responded: boolean
  response?: string
}

interface Annotation {
  id: string
  feature_id?: string
  type: 'bug' | 'comment' | 'workaround' | 'idea'
  content: string
  created_at: string
  resolved: boolean
}

interface ChatMessage {
  id: string
  project: string
  role: 'human' | 'agent'
  content: string
  created_at: string
}

interface DevLayerProps {
  projects: Project[]
  selectedProject: string | null
  onSelectProject: (name: string) => void
}

const priorityColors = {
  critical: 'bg-red-500 text-white',
  normal: 'bg-yellow-400 text-black',
  low: 'bg-gray-300 text-black'
}

const annotationIcons = {
  bug: Bug,
  comment: StickyNote,
  workaround: AlertCircle,
  idea: Lightbulb
}

const annotationColors = {
  bug: 'border-red-500 bg-red-50 dark:bg-red-950',
  comment: 'border-blue-500 bg-blue-50 dark:bg-blue-950',
  workaround: 'border-orange-500 bg-orange-50 dark:bg-orange-950',
  idea: 'border-purple-500 bg-purple-50 dark:bg-purple-950'
}

export function DevLayer({ projects, selectedProject, onSelectProject }: DevLayerProps) {
  const queryClient = useQueryClient()
  const [chatInput, setChatInput] = useState('')
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set())
  const [viewAll, setViewAll] = useState(!selectedProject)
  const [mutedProjects, setMutedProjects] = useState<Set<string>>(() => {
    const saved = localStorage.getItem('devlayer-muted')
    return saved ? new Set(JSON.parse(saved)) : new Set()
  })

  // Fetch all agent requests across projects
  const { data: allRequests = [] } = useQuery<AgentRequest[]>({
    queryKey: ['devlayer', 'requests'],
    queryFn: async () => {
      const res = await fetch('/api/devlayer/requests')
      if (!res.ok) return []
      return res.json()
    },
    refetchInterval: 3000
  })

  // Fetch chat messages for selected project
  const { data: chatMessages = [] } = useQuery<ChatMessage[]>({
    queryKey: ['devlayer', 'chat', selectedProject],
    queryFn: async () => {
      if (!selectedProject) return []
      const res = await fetch(`/api/devlayer/projects/${encodeURIComponent(selectedProject)}/chat`)
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!selectedProject,
    refetchInterval: 2000
  })

  // Fetch annotations for selected project
  const { data: annotations = [] } = useQuery<Annotation[]>({
    queryKey: ['devlayer', 'annotations', selectedProject],
    queryFn: async () => {
      if (!selectedProject) return []
      const res = await fetch(`/api/devlayer/projects/${encodeURIComponent(selectedProject)}/annotations`)
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!selectedProject
  })

  // Send chat message
  const sendMessage = useMutation({
    mutationFn: async (content: string) => {
      const res = await fetch(`/api/devlayer/projects/${encodeURIComponent(selectedProject!)}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      })
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devlayer', 'chat', selectedProject] })
      setChatInput('')
    }
  })

  // Respond to agent request
  const respondToRequest = useMutation({
    mutationFn: async ({ id, response }: { id: string, response: string }) => {
      const res = await fetch(`/api/devlayer/requests/${id}/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ response })
      })
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devlayer', 'requests'] })
    }
  })

  // Add annotation
  const addAnnotation = useMutation({
    mutationFn: async (data: { type: Annotation['type'], content: string, feature_id?: string }) => {
      const res = await fetch(`/api/devlayer/projects/${encodeURIComponent(selectedProject!)}/annotations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devlayer', 'annotations', selectedProject] })
    }
  })

  // Save muted projects to localStorage
  useEffect(() => {
    localStorage.setItem('devlayer-muted', JSON.stringify([...mutedProjects]))
  }, [mutedProjects])

  const toggleMute = (project: string) => {
    setMutedProjects(prev => {
      const next = new Set(prev)
      if (next.has(project)) next.delete(project)
      else next.add(project)
      return next
    })
  }

  const toggleExpand = (project: string) => {
    setExpandedProjects(prev => {
      const next = new Set(prev)
      if (next.has(project)) next.delete(project)
      else next.add(project)
      return next
    })
  }

  // Filter requests by muted status
  const activeRequests = allRequests.filter(r => !r.responded && !mutedProjects.has(r.project))
  const criticalRequests = activeRequests.filter(r => r.priority === 'critical')
  const normalRequests = activeRequests.filter(r => r.priority !== 'critical')

  // Group requests by project for dashboard
  const requestsByProject = allRequests.reduce((acc, req) => {
    if (!acc[req.project]) acc[req.project] = []
    acc[req.project].push(req)
    return acc
  }, {} as Record<string, AgentRequest[]>)

  // Tab bar for switching views
  const TabBar = () => (
    <div className="flex gap-2 p-3 border-b border-gray-200 dark:border-gray-700">
      <button
        onClick={() => setViewAll(true)}
        className={`px-4 py-2 rounded font-medium ${viewAll ? 'bg-purple-500 text-white' : 'bg-gray-200 dark:bg-gray-700'}`}
      >
        All Projects ({projects.length})
      </button>
      {selectedProject && (
        <button
          onClick={() => setViewAll(false)}
          className={`px-4 py-2 rounded font-medium ${!viewAll ? 'bg-purple-500 text-white' : 'bg-gray-200 dark:bg-gray-700'}`}
        >
          {selectedProject}
        </button>
      )}
    </div>
  )

  if (viewAll) {
    // Multi-project dashboard view
    return (
      <div className="h-full flex flex-col">
        <TabBar />
        <div className="flex-1 overflow-auto p-4">
        {/* Attention Queue */}
        {activeRequests.length > 0 && (
          <div className="mb-6">
            <h2 className="text-lg font-bold mb-3 flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-red-500" />
              Attention Queue ({activeRequests.length})
            </h2>

            {/* Critical requests */}
            {criticalRequests.length > 0 && (
              <div className="space-y-2 mb-4">
                {criticalRequests.map(req => (
                  <RequestCard key={req.id} request={req} onRespond={respondToRequest.mutate} />
                ))}
              </div>
            )}

            {/* Normal requests */}
            {normalRequests.length > 0 && (
              <div className="space-y-2">
                {normalRequests.map(req => (
                  <RequestCard key={req.id} request={req} onRespond={respondToRequest.mutate} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* All Projects */}
        <h2 className="text-lg font-bold mb-3">All Projects ({projects.length})</h2>
        <div className="grid gap-3">
          {projects.map(project => {
            const projectRequests = requestsByProject[project.name] || []
            const pendingRequests = projectRequests.filter(r => !r.responded)
            const isMuted = mutedProjects.has(project.name)
            const isExpanded = expandedProjects.has(project.name)

            return (
              <div
                key={project.name}
                className="neo-card p-3 cursor-pointer hover:shadow-lg transition-shadow"
              >
                <div className="flex items-center justify-between">
                  <div
                    className="flex items-center gap-2 flex-1"
                    onClick={() => onSelectProject(project.name)}
                  >
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleExpand(project.name) }}
                      className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
                    >
                      {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    </button>
                    <span className="font-medium">{project.name}</span>
                    {pendingRequests.length > 0 && (
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                        pendingRequests.some(r => r.priority === 'critical')
                          ? 'bg-red-500 text-white'
                          : 'bg-yellow-400 text-black'
                      }`}>
                        {pendingRequests.length} pending
                      </span>
                    )}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleMute(project.name) }}
                    className={`p-2 rounded ${isMuted ? 'text-gray-400' : 'text-gray-600 dark:text-gray-300'}`}
                    title={isMuted ? 'Unmute notifications' : 'Mute notifications'}
                  >
                    {isMuted ? <BellOff className="w-4 h-4" /> : <Bell className="w-4 h-4" />}
                  </button>
                </div>

                {isExpanded && pendingRequests.length > 0 && (
                  <div className="mt-3 pl-7 space-y-2">
                    {pendingRequests.slice(0, 3).map(req => (
                      <div key={req.id} className="text-sm p-2 bg-gray-100 dark:bg-gray-800 rounded">
                        <span className={`text-xs px-1.5 py-0.5 rounded mr-2 ${priorityColors[req.priority]}`}>
                          {req.type}
                        </span>
                        {req.message.slice(0, 100)}...
                      </div>
                    ))}
                    {pendingRequests.length > 3 && (
                      <div className="text-sm text-gray-500">
                        +{pendingRequests.length - 3} more
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
        </div>
      </div>
    )
  }

  // Single project view - guard against null
  const currentProject = selectedProject || ''
  if (!currentProject) {
    setViewAll(true)
    return null
  }

  return (
    <div className="h-full flex flex-col">
      <TabBar />
      {/* Project Header */}
      <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <h2 className="font-bold">{currentProject}</h2>
        <button
          onClick={() => toggleMute(currentProject)}
          className={`p-2 rounded ${mutedProjects.has(currentProject) ? 'text-gray-400' : ''}`}
        >
          {mutedProjects.has(currentProject) ? <BellOff className="w-4 h-4" /> : <Bell className="w-4 h-4" />}
        </button>
      </div>

      {/* Pending Requests for this project */}
      {requestsByProject[currentProject]?.filter((r: AgentRequest) => !r.responded).length > 0 && (
        <div className="p-3 border-b border-gray-200 dark:border-gray-700 bg-yellow-50 dark:bg-yellow-950">
          <h3 className="font-medium mb-2 flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            Pending Requests
          </h3>
          <div className="space-y-2">
            {requestsByProject[currentProject]?.filter((r: AgentRequest) => !r.responded).map((req: AgentRequest) => (
              <RequestCard key={req.id} request={req} onRespond={respondToRequest.mutate} compact />
            ))}
          </div>
        </div>
      )}

      {/* Annotations */}
      {annotations.length > 0 && (
        <div className="p-3 border-b border-gray-200 dark:border-gray-700">
          <h3 className="font-medium mb-2">Annotations</h3>
          <div className="space-y-2 max-h-32 overflow-y-auto">
            {annotations.filter(a => !a.resolved).map(ann => {
              const Icon = annotationIcons[ann.type]
              return (
                <div key={ann.id} className={`p-2 rounded border-l-4 ${annotationColors[ann.type]}`}>
                  <div className="flex items-center gap-2 text-sm">
                    <Icon className="w-4 h-4" />
                    <span className="font-medium capitalize">{ann.type}</span>
                  </div>
                  <p className="text-sm mt-1">{ann.content}</p>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {chatMessages.map(msg => (
          <div
            key={msg.id}
            className={`p-2 rounded max-w-[80%] ${
              msg.role === 'human'
                ? 'ml-auto bg-blue-500 text-white'
                : 'bg-gray-200 dark:bg-gray-700'
            }`}
          >
            <p className="text-sm">{msg.content}</p>
            <span className="text-xs opacity-70">
              {new Date(msg.created_at).toLocaleTimeString()}
            </span>
          </div>
        ))}
      </div>

      {/* Chat Input */}
      <div className="p-3 border-t border-gray-200 dark:border-gray-700">
        <div className="flex gap-2">
          <input
            type="text"
            value={chatInput}
            onChange={e => setChatInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && chatInput.trim()) {
                sendMessage.mutate(chatInput.trim())
              }
            }}
            placeholder="Send message to agent..."
            className="flex-1 px-3 py-2 border rounded dark:bg-gray-800 dark:border-gray-600"
          />
          <button
            onClick={() => chatInput.trim() && sendMessage.mutate(chatInput.trim())}
            disabled={!chatInput.trim() || sendMessage.isPending}
            className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>

        {/* Quick annotation buttons */}
        <div className="flex gap-2 mt-2">
          {(['bug', 'comment', 'workaround', 'idea'] as const).map(type => {
            const Icon = annotationIcons[type]
            return (
              <button
                key={type}
                onClick={() => {
                  const content = prompt(`Add ${type}:`)
                  if (content) addAnnotation.mutate({ type, content })
                }}
                className="flex items-center gap-1 px-2 py-1 text-xs border rounded hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                <Icon className="w-3 h-3" />
                {type}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// Request card component
function RequestCard({
  request,
  onRespond,
  compact = false
}: {
  request: AgentRequest
  onRespond: (data: { id: string, response: string }) => void
  compact?: boolean
}) {
  const [response, setResponse] = useState('')
  const [isResponding, setIsResponding] = useState(false)

  return (
    <div className={`neo-card p-3 border-l-4 ${
      request.priority === 'critical' ? 'border-l-red-500' : 'border-l-yellow-400'
    }`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${priorityColors[request.priority]}`}>
              {request.priority}
            </span>
            <span className="text-xs text-gray-500">{request.type}</span>
            {!compact && <span className="text-xs text-gray-400">{request.project}</span>}
          </div>
          <p className={compact ? 'text-sm' : ''}>{request.message}</p>
          {request.context && !compact && (
            <p className="text-sm text-gray-500 mt-1">{request.context}</p>
          )}
        </div>
        <span className="text-xs text-gray-400 whitespace-nowrap">
          {new Date(request.created_at).toLocaleTimeString()}
        </span>
      </div>

      {isResponding ? (
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={response}
            onChange={e => setResponse(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && response.trim()) {
                onRespond({ id: request.id, response: response.trim() })
                setIsResponding(false)
                setResponse('')
              }
            }}
            placeholder="Type your response..."
            className="flex-1 px-2 py-1 text-sm border rounded dark:bg-gray-800"
            autoFocus
          />
          <button
            onClick={() => {
              if (response.trim()) {
                onRespond({ id: request.id, response: response.trim() })
                setIsResponding(false)
                setResponse('')
              }
            }}
            className="px-3 py-1 text-sm bg-green-500 text-white rounded"
          >
            Send
          </button>
          <button
            onClick={() => { setIsResponding(false); setResponse('') }}
            className="px-3 py-1 text-sm border rounded"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          onClick={() => setIsResponding(true)}
          className="mt-2 px-3 py-1 text-sm bg-blue-500 text-white rounded"
        >
          Respond
        </button>
      )}
    </div>
  )
}

export default DevLayer
