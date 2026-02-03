import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Server, PlayCircle, StopCircle, Loader2, RefreshCw, ExternalLink } from 'lucide-react'

interface DevServerStatus {
  project: string
  path: string
  port: number | null
  status: 'running' | 'stopped'
  url: string | null
  has_spec: boolean
  spec_path: string | null
  project_type: string
  features_total: number
  features_passing: number
  completion_percentage: number
  has_features_db: boolean
  agent_running: boolean
  agent_session: string | null
}

interface StatusResponse {
  servers: DevServerStatus[]
  count: number
  summary: {
    running: number
    agents: number
    idle: number
  }
}

interface StatusTabProps {
  selectedProject: string | null
}

export function StatusTab({ selectedProject }: StatusTabProps) {
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Fetch project status data
  const { data: statusData, isLoading, refetch } = useQuery<StatusResponse>({
    queryKey: ['projectStatus'],
    queryFn: async () => {
      const res = await fetch('/api/status/devservers')
      if (!res.ok) {
        throw new Error('Failed to fetch status')
      }
      return res.json()
    },
    refetchInterval: autoRefresh ? 5000 : false,
  })

  // Find current project
  const currentProject = statusData?.servers?.find(p => p.project === selectedProject)

  // Calculate health based on completion percentage
  const getHealthStatus = (percentage: number) => {
    if (percentage === 0) return { color: 'bg-gray-400', label: 'Not Started' }
    if (percentage < 50) return { color: 'bg-yellow-500', label: 'In Progress' }
    if (percentage < 100) return { color: 'bg-blue-500', label: 'Making Progress' }
    return { color: 'bg-green-500', label: 'Complete' }
  }

  if (!selectedProject) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <p className="text-lg mb-2">No project selected</p>
          <p className="text-sm">Select a project to view status</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Project Status
            </h2>
            <p className="text-sm text-gray-500">
              {selectedProject}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Auto-refresh Toggle */}
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded border-gray-300"
              />
              Auto-refresh
            </label>

            {/* Manual Refresh */}
            <button
              onClick={() => refetch()}
              className="neo-btn px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 flex items-center gap-2"
              title="Refresh status"
            >
              <RefreshCw size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="animate-spin text-gray-400" size={32} />
          </div>
        )}

        {!isLoading && !currentProject && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <Server className="text-yellow-600 dark:text-yellow-500 flex-shrink-0" size={20} />
              <div>
                <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
                  Project not found
                </p>
                <p className="text-sm text-yellow-700 dark:text-yellow-300 mt-1">
                  Project &quot;{selectedProject}&quot; is not registered in the system.
                </p>
              </div>
            </div>
          </div>
        )}

        {!isLoading && currentProject && (
          <div className="space-y-6">
            {/* Health Overview */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                Health Status
              </h3>
              <div className="flex items-center gap-4">
                <div className={`w-3 h-3 rounded-full ${getHealthStatus(currentProject.completion_percentage).color}`} />
                <span className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {getHealthStatus(currentProject.completion_percentage).label}
                </span>
              </div>
            </div>

            {/* Dev Server Status */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                Development Server
              </h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-700 dark:text-gray-300">Port</p>
                    <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                      {currentProject.port || 'Not assigned'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${currentProject.status === 'running' ? 'bg-green-500' : 'bg-gray-400'}`} />
                    <span className={`text-sm font-medium ${currentProject.status === 'running' ? 'text-green-600' : 'text-gray-500'}`}>
                      {currentProject.status === 'running' ? 'Running' : 'Stopped'}
                    </span>
                  </div>
                </div>

                {currentProject.port && currentProject.url && (
                  <div className="flex gap-2">
                    {currentProject.status === 'stopped' && (
                      <button className="neo-btn px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2" disabled>
                        <PlayCircle size={18} />
                        Start Server
                      </button>
                    )}
                    {currentProject.status === 'running' && (
                      <>
                        <button className="neo-btn px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 flex items-center gap-2" disabled>
                          <StopCircle size={18} />
                          Stop Server
                        </button>
                        <a
                          href={currentProject.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="neo-btn px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 flex items-center gap-2"
                        >
                          <ExternalLink size={18} />
                          Open {currentProject.port}
                        </a>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Feature Progress */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                Feature Progress
              </h3>
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      {currentProject.features_passing} of {currentProject.features_total} features complete
                    </span>
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {currentProject.completion_percentage}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
                    <div
                      className="bg-gradient-to-r from-purple-500 to-purple-600 h-3 rounded-full transition-all duration-300"
                      style={{ width: `${currentProject.completion_percentage}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Agent Status */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                Agent Status
              </h3>
              <div className="flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full ${currentProject.agent_running ? 'bg-green-500' : 'bg-gray-400'}`} />
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {currentProject.agent_running ? 'Agent Running' : 'Agent Idle'}
                  </p>
                  {currentProject.agent_session && (
                    <p className="text-xs text-gray-500">
                      Session: {currentProject.agent_session}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Project Info */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                Project Details
              </h3>
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-gray-600 dark:text-gray-400">Path:</dt>
                  <dd className="text-gray-900 dark:text-gray-100 font-mono text-xs">
                    {currentProject.path}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-600 dark:text-gray-400">Type:</dt>
                  <dd className="text-gray-900 dark:text-gray-100">
                    {currentProject.project_type || 'Unknown'}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-600 dark:text-gray-400">Has Spec:</dt>
                  <dd className="text-gray-900 dark:text-gray-100">
                    {currentProject.has_spec ? 'Yes' : 'No'}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
