import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TrendingUp, Activity, Target, Calendar } from 'lucide-react'

interface AnalyticsData {
  project: string
  period: {
    start: string
    end: string
    days: number
  }
  created: Array<{ date: string; count: number }>
  completed: Array<{ date: string; count: number }>
  cumulative: {
    created: Array<{ date: string; total: number }>
    completed: Array<{ date: string; total: number }>
  }
}

interface ThroughputData {
  project: string
  period_days: number
  features_completed: number
  features_created: number
  completion_rate: number
  average_per_day: number
  current_streak: number
  total_features: number
  percentage_complete: number
}

interface AnalyticsTabProps {
  selectedProject: string | null
}

export function AnalyticsTab({ selectedProject }: AnalyticsTabProps) {
  const [days, setDays] = useState(30)

  const { data: analytics, isLoading: analyticsLoading } = useQuery<AnalyticsData>({
    queryKey: ['analytics', 'features', selectedProject, days],
    queryFn: async () => {
      if (!selectedProject) return null
      const res = await fetch(`/api/analytics/features/${encodeURIComponent(selectedProject)}?days=${days}`)
      if (!res.ok) throw new Error('Failed to fetch analytics')
      return res.json()
    },
    enabled: !!selectedProject,
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  const { data: throughput, isLoading: throughputLoading } = useQuery<ThroughputData>({
    queryKey: ['analytics', 'throughput', selectedProject, days],
    queryFn: async () => {
      if (!selectedProject) return null
      const res = await fetch(`/api/analytics/throughput/${encodeURIComponent(selectedProject)}?days=${days}`)
      if (!res.ok) throw new Error('Failed to fetch throughput')
      return res.json()
    },
    enabled: !!selectedProject,
    refetchInterval: 30000,
  })

  if (!selectedProject) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <Activity size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-lg mb-2">No project selected</p>
          <p className="text-sm">Select a project to view analytics</p>
        </div>
      </div>
    )
  }

  if (analyticsLoading || throughputLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
      </div>
    )
  }

  // Prepare chart data
  const cumulativeChartData = analytics?.cumulative?.created?.map((item, index) => ({
    date: item.date,
    Created: item.total,
    Completed: analytics?.cumulative?.completed?.[index]?.total || 0
  })) || []

  const dailyChartData = analytics?.created?.map((item, index) => ({
    date: item.date,
    Created: item.count,
    Completed: analytics?.completed?.[index]?.count || 0
  })) || []

  return (
    <div className="flex flex-col h-full bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Project Analytics
            </h2>
            <p className="text-sm text-gray-500">
              {selectedProject}
            </p>
          </div>

          {/* Time range selector */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600 dark:text-gray-400">
              <Calendar size={16} className="inline mr-1" />
              Period:
            </label>
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="px-3 py-1 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 text-sm"
            >
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
              <option value={60}>60 days</option>
              <option value={90}>90 days</option>
            </select>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Summary Stats */}
        {throughput && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 dark:bg-green-900/20 rounded-lg">
                  <TrendingUp className="text-green-600 dark:text-green-400" size={20} />
                </div>
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Completed</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                    {throughput.features_completed}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-900/20 rounded-lg">
                  <Activity className="text-blue-600 dark:text-blue-400" size={20} />
                </div>
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Created</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                    {throughput.features_created}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-100 dark:bg-purple-900/20 rounded-lg">
                  <Target className="text-purple-600 dark:text-purple-400" size={20} />
                </div>
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Avg/Day</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                    {throughput.average_per_day}
                  </p>
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-orange-100 dark:bg-orange-900/20 rounded-lg">
                  <Calendar className="text-orange-600 dark:text-orange-400" size={20} />
                </div>
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Streak</p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                    {throughput.current_streak}d
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Cumulative Progress Chart */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Cumulative Progress
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={cumulativeChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="date"
                stroke="#9CA3AF"
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
              />
              <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF', fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#F9FAFB'
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="Created"
                stroke="#3B82F6"
                strokeWidth={2}
                dot={{ fill: '#3B82F6', r: 4 }}
                activeDot={{ r: 6 }}
              />
              <Line
                type="monotone"
                dataKey="Completed"
                stroke="#10B981"
                strokeWidth={2}
                dot={{ fill: '#10B981', r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Daily Activity Chart */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Daily Activity
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={dailyChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="date"
                stroke="#9CA3AF"
                tick={{ fill: '#9CA3AF', fontSize: 12 }}
              />
              <YAxis stroke="#9CA3AF" tick={{ fill: '#9CA3AF', fontSize: 12 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#F9FAFB'
                }}
              />
              <Legend />
              <Bar dataKey="Created" fill="#3B82F6" radius={[8, 8, 0, 0]} />
              <Bar dataKey="Completed" fill="#10B981" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Detailed Stats */}
        {throughput && (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              Performance Metrics
            </h3>
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-600 dark:text-gray-400">Completion Rate:</dt>
                <dd className="font-semibold text-gray-900 dark:text-gray-100">
                  {(throughput.completion_rate * 100).toFixed(1)}%
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-600 dark:text-gray-400">Total Features:</dt>
                <dd className="font-semibold text-gray-900 dark:text-gray-100">
                  {throughput.total_features}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-600 dark:text-gray-400">Percentage Complete:</dt>
                <dd className="font-semibold text-gray-900 dark:text-gray-100">
                  {throughput.percentage_complete}%
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-600 dark:text-gray-400">Period:</dt>
                <dd className="font-semibold text-gray-900 dark:text-gray-100">
                  {throughput.period_days} days
                </dd>
              </div>
            </dl>
          </div>
        )}
      </div>
    </div>
  )
}
