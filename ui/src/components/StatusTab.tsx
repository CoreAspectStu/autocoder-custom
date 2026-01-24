import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Server, PlayCircle, StopCircle, Loader2, RefreshCw, AlertCircle } from 'lucide-react'

interface ProjectStatus {
  name: string
  path: string
  port: number | null
  is_running: boolean
  health: 'green' | 'yellow' | 'red' | 'gray'
  progress: {
    total: number
    passing: number
    percentage: number
  }
  agent_status: 'running' | 'idle'
}

interface StatusTabProps {
  selectedProject: string | null
}

export function StatusTab({ selectedProject }: StatusTabProps) {
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Fetch project status data
  const { data: projects = [], isLoading, refetch } = useQuery<ProjectStatus[]>({
    queryKey: ['projectStatus'],
    queryFn: async () => {
      const res = await fetch('/api/status/json')
      if (!res.ok) {
        // If JSON endpoint doesn't exist yet, return empty array
        console.warn('/api/status/json not implemented yet')
        return []
      }
      return res.json()
    },
    refetchInterval: autoRefresh ? 5000 : false,
  })

  // Find current project
  const currentProject = projects.find(p => p.name === selectedProject)

  const getHealthColor = (health: string) => {
    switch (health) {
      case 'green': return 'bg-green-500'
      case 'yellow': return 'bg-yellow-500'
      case 'red': return 'bg-red-500'
      default: return 'bg-gray-400'
    }
  }

  const getHealthLabel = (health: string) => {
    switch (health) {
      case 'green': return 'Healthy'
      case 'yellow': return 'In Progress'
      case 'red': return 'Issues'
      default: return 'Not Started'
    }
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

        {!isLoading && projects.length === 0 && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="text-yellow-600 dark:text-yellow-500 flex-shrink-0" size={20} />
              <div>
                <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
                  Status API Not Implemented
                </p>
                <p className="text-sm text-yellow-700 dark:text-yellow-300 mt-1">
                  The <code className="bg-yellow-100 dark:bg-yellow-900 px-1 rounded">/api/status/json</code> endpoint needs to be created.
                  This will expose the same data as <code className="bg-yellow-100 dark:bg-yellow-900 px-1 rounded">/status</code> but in JSON format.
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
                <div className={`w-3 h-3 rounded-full ${getHealthColor(currentProject.health)}`} />
                <span className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {getHealthLabel(currentProject.health)}
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
                    <div className={`w-2 h-2 rounded-full ${currentProject.is_running ? 'bg-green-500' : 'bg-gray-400'}`} />
                    <span className={`text-sm font-medium ${currentProject.is_running ? 'text-green-600' : 'text-gray-500'}`}>
                      {currentProject.is_running ? 'Running' : 'Stopped'}
                    </span>
                  </div>
                </div>

                {currentProject.port && (
                  <div className="flex gap-2">
                    {!currentProject.is_running && (
                      <button className="neo-btn px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 flex items-center gap-2">
                        <PlayCircle size={18} />
                        Start Server
                      </button>
                    )}
                    {currentProject.is_running && (
                      <>
                        <button className="neo-btn px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 flex items-center gap-2">
                          <StopCircle size={18} />
                          Stop Server
                        </button>
                        <a
                          href={`http://localhost:${currentProject.port}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="neo-btn px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 flex items-center gap-2"
                        >
                          <Server size={18} />
                          Open App
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
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600 dark:text-gray-400">Completion</span>
                  <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                    {currentProject.progress.percentage}%
                  </span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
                  <div
                    className="bg-purple-500 h-3 rounded-full transition-all duration-500"
                    style={{ width: `${currentProject.progress.percentage}%` }}
                  />
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600 dark:text-gray-400">
                    {currentProject.progress.passing} of {currentProject.progress.total} features
                  </span>
                  <span className={`font-medium ${
                    currentProject.agent_status === 'running'
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-gray-500'
                  }`}>
                    Agent: {currentProject.agent_status}
                  </span>
                </div>
              </div>
            </div>

            {/* Quick Links */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
                Quick Actions
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <a
                  href="/status"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="neo-btn px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 text-center"
                >
                  View Full Status Dashboard
                </a>
                <button className="neo-btn px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600">
                  View Logs
                </button>
              </div>
            </div>
          </div>
        )}

        {!isLoading && !currentProject && projects.length > 0 && (
          <div className="text-center text-gray-500 py-8">
            <p className="text-lg mb-2">Project not found in status data</p>
            <p className="text-sm">Select a different project or check the server</p>
          </div>
        )}
      </div>
    </div>
  )
}
