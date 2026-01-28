import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Zap, Clock, TrendingUp, RefreshCw } from 'lucide-react'

interface QualityMetrics {
  devlayer_triage_count: number
  devlayer_approved_count: number
  dev_active_cards: number
  dev_completed_cards: number
  pipeline_velocity_hours: Record<string, number>
  cards_in_pipeline: number
}

interface PipelineEvent {
  id: string
  event_type: string
  card_id: string
  from_stage?: string
  to_stage?: string
  result?: string
  evidence: Record<string, any>
  created_at: string
}

interface PipelineDashboardProps {
  project?: string
}

export function PipelineDashboard({ project: _project }: PipelineDashboardProps) {
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Show warning if no project is selected
  if (!_project) {
    return (
      <div className="p-6 bg-white dark:bg-gray-800 rounded-lg text-center">
        <Activity className="w-12 h-12 mx-auto text-gray-400 mb-4" />
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
          No Project Selected
        </h3>
        <p className="text-gray-600 dark:text-gray-400">
          Please select a project from the dropdown to use the Quality Pipeline Dashboard.
        </p>
      </div>
    )
  }

  // Fetch metrics
  const { data: metrics, refetch: refetchMetrics } = useQuery<QualityMetrics>({
    queryKey: ['quality', 'metrics'],
    queryFn: async () => {
      const res = await fetch('/api/quality/metrics')
      if (!res.ok) throw new Error('Failed to fetch metrics')
      const data = await res.json()
      return data.metrics
    },
    refetchInterval: autoRefresh ? 30000 : false
  })

  // Fetch board stats for breakdown
  const { data: boardStats = {}, refetch: refetchStats } = useQuery<Record<string, number>>({
    queryKey: ['quality', 'stats'],
    queryFn: async () => {
      const res = await fetch('/api/quality/stats')
      if (!res.ok) throw new Error('Failed to fetch stats')
      return res.json()
    },
    refetchInterval: autoRefresh ? 30000 : false
  })

  // Fetch pipeline events
  const { data: events = [] } = useQuery<PipelineEvent[]>({
    queryKey: ['quality', 'events'],
    queryFn: async () => {
      const res = await fetch('/api/quality/pipeline/events?limit=20')
      if (!res.ok) throw new Error('Failed to fetch events')
      return res.json()
    },
    refetchInterval: autoRefresh ? 5000 : false
  })

  const eventColors = {
    uat_failure: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    devlayer_approval: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    dev_complete: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    uat_retest: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
  }

  const getVelocityColor = (hours: number | null) => {
    if (hours === null || hours === undefined) return 'text-gray-400'
    if (hours < 4) return 'text-green-600'
    if (hours < 24) return 'text-yellow-600'
    return 'text-red-600'
  }

  return (
    <div className="p-6 bg-white dark:bg-gray-800 rounded-lg">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Activity className="w-6 h-6" />
            Quality Pipeline Dashboard
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Real-time view of cards in the quality gate workflow
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { refetchMetrics(); refetchStats() }}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
            title="Refresh"
          >
            <RefreshCw className="w-5 h-5" />
          </button>
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-3 py-1.5 text-sm rounded flex items-center gap-2 ${
              autoRefresh ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
            }`}
          >
            <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
            Auto-refresh: {autoRefresh ? 'On' : 'Off'}
          </button>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        {/* Pipeline Cards */}
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">Cards in Pipeline</span>
            <TrendingUp className="w-4 h-4 text-blue-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {metrics?.cards_in_pipeline || 0}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Across all stages
          </p>
        </div>

        {/* Triage Queue */}
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">Triage Queue</span>
            <Clock className="w-4 h-4 text-yellow-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {boardStats?.triage || 0}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Awaiting triage
          </p>
        </div>

        {/* Dev Active */}
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">Dev Active</span>
            <Zap className="w-4 h-4 text-purple-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {metrics?.dev_active_cards || 0}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Currently working
          </p>
        </div>
      </div>

      {/* Pipeline Flow */}
      <div className="mb-6 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Pipeline Flow
        </h3>
        <div className="flex items-center justify-between text-sm overflow-x-auto">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-4 py-2 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg">
              <span className="font-medium">DevLayer</span>
              <span className="text-gray-600 dark:text-gray-400">→</span>
            </div>
            <div className="text-2xl">→</div>
            <div className="flex items-center gap-2 px-4 py-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
              <span className="font-medium">Dev</span>
              <span className="text-gray-600 dark:text-gray-400">→</span>
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline Velocity */}
      {metrics?.pipeline_velocity_hours && Object.keys(metrics.pipeline_velocity_hours).length > 0 && (
        <div className="mb-6 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Pipeline Velocity
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">Average time in each stage</p>
          <div className="space-y-2">
            {Object.entries(metrics.pipeline_velocity_hours)
              .filter(([_, hours]) => hours !== null)
              .map(([stage, hours]) => (
              <div key={stage} className="flex items-center gap-4">
                <span className="w-24 text-sm text-gray-700 dark:text-gray-300 capitalize">{stage}</span>
                <div className="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-4">
                  <div
                    className="bg-blue-500 h-4 rounded-full"
                    style={{ width: `${Math.min(hours * 10, 100)}%` }}
                  />
                </div>
                <span className={`text-sm font-medium ${getVelocityColor(hours)}`}>
                  {hours.toFixed(1)}h
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Events */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Recent Pipeline Events
        </h3>
        <div className="space-y-2">
          {events.slice(0, 10).map((event) => (
            <div
              key={event.id}
              className={`p-3 rounded border ${
                eventColors[event.event_type as keyof typeof eventColors] ||
                'bg-gray-50 dark:bg-gray-700'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium capitalize">
                  {event.event_type.replace(/_/g, ' ')}
                </span>
                <span className="text-xs text-gray-500">
                  {new Date(event.created_at).toLocaleTimeString()}
                </span>
              </div>
              <div className="text-sm text-gray-700 dark:text-gray-300">
                Card: {event.card_id}
                {event.from_stage && event.to_stage && (
                  <span className="ml-2">
                    {event.from_stage} → {event.to_stage}
                  </span>
                )}
                {event.result && (
                  <span className={`ml-2 font-medium ${
                    event.result === 'pass' ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {event.result === 'pass' ? '✓' : '✗'} {event.result}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
        {events.length === 0 && (
          <p className="text-sm text-gray-500 text-center py-4">
            No events yet
          </p>
        )}
      </div>
    </div>
  )
}
