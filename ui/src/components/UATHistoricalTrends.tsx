/**
 * UAT Historical Trends Component
 *
 * Displays UAT test results over time with trend analysis.
 * Shows pass rates, failure patterns, and flaky test detection.
 */

import { useState, useMemo } from 'react'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  Calendar,
  Filter
} from 'lucide-react'

export interface TrendDataPoint {
  date: string
  cycle_id: string
  total_tests: number
  passed_tests: number
  failed_tests: number
  pass_rate: number
  duration_seconds: number
}

export interface FlakyTest {
  test_id: string
  test_name: string
  total_runs: number
  passed_runs: number
  failed_runs: number
  flakiness_score: number
  last_failure?: string
}

export interface FailurePattern {
  category: string
  count: number
  trend: 'increasing' | 'decreasing' | 'stable'
  examples: string[]
}

interface UATHistoricalTrendsProps {
  projectId: string
  timeRange: '7d' | '30d' | '90d' | 'all'
  onTimeRangeChange?: (range: '7d' | '30d' | '90d' | 'all') => void
}

export function UATHistoricalTrends({ projectId, timeRange, onTimeRangeChange }: UATHistoricalTrendsProps) {
  const [selectedView, setSelectedView] = useState<'overview' | 'flaky' | 'patterns'>('overview')

  // Sample data - in production, this would come from the API
  const trendData: TrendDataPoint[] = useMemo(() => {
    const data: TrendDataPoint[] = []
    const now = new Date()
    for (let i = 29; i >= 0; i--) {
      const date = new Date(now)
      date.setDate(date.getDate() - i)
      data.push({
        date: date.toISOString().split('T')[0],
        cycle_id: `cycle-${i}`,
        total_tests: 40 + Math.floor(Math.random() * 10),
        passed_tests: 35 + Math.floor(Math.random() * 8),
        failed_tests: Math.floor(Math.random() * 5),
        pass_rate: 85 + Math.random() * 12,
        duration_seconds: 200 + Math.random() * 100
      })
    }
    return data
  }, [])

  const flakyTests: FlakyTest[] = [
    {
      test_id: 'test-1',
      test_name: 'Login with social provider',
      total_runs: 30,
      passed_runs: 24,
      failed_runs: 6,
      flakiness_score: 20,
      last_failure: '2 days ago'
    },
    {
      test_id: 'test-2',
      test_name: 'Checkout flow',
      total_runs: 25,
      passed_runs: 22,
      failed_runs: 3,
      flakiness_score: 12,
      last_failure: '5 days ago'
    }
  ]

  const failurePatterns: FailurePattern[] = [
    {
      category: 'Timeout',
      count: 15,
      trend: 'decreasing',
      examples: ['API timeout', 'Element load timeout']
    },
    {
      category: 'Selector Issues',
      count: 8,
      trend: 'stable',
      examples: ['#submit-button not found', '.modal-content changed']
    },
    {
      category: 'Network Errors',
      count: 5,
      trend: 'increasing',
      examples: ['500 Internal Server Error', 'Connection refused']
    }
  ]

  const stats = useMemo(() => {
    if (trendData.length === 0) return null

    const latest = trendData[trendData.length - 1]
    const previous = trendData[Math.max(0, trendData.length - 2)]

    const avgPassRate = trendData.reduce((sum, d) => sum + d.pass_rate, 0) / trendData.length
    const trend: 'up' | 'down' | 'stable' = latest.pass_rate > previous.pass_rate ? 'up' : latest.pass_rate < previous.pass_rate ? 'down' : 'stable'

    return {
      current: latest.pass_rate,
      previous: previous.pass_rate,
      average: avgPassRate,
      trend,
      change: Math.abs(latest.pass_rate - previous.pass_rate)
    }
  }, [trendData])

  const getTrendIcon = (trend: 'up' | 'down' | 'stable') => {
    switch (trend) {
      case 'up':
        return <TrendingUp className="w-4 h-4 text-green-600 dark:text-green-400" />
      case 'down':
        return <TrendingDown className="w-4 h-4 text-red-600 dark:text-red-400" />
      default:
        return <Minus className="w-4 h-4 text-gray-600 dark:text-gray-400" />
    }
  }

  const getPatternTrendIcon = (trend: 'increasing' | 'decreasing' | 'stable') => {
    switch (trend) {
      case 'increasing':
        return <TrendingUp className="w-4 h-4 text-red-600 dark:text-red-400" />
      case 'decreasing':
        return <TrendingDown className="w-4 h-4 text-green-600 dark:text-green-400" />
      default:
        return <Minus className="w-4 h-4 text-gray-600 dark:text-gray-400" />
    }
  }

  const getFlakinessColor = (score: number) => {
    if (score >= 20) return 'text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30'
    if (score >= 10) return 'text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-900/30'
    return 'text-yellow-600 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900/30'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Historical Trends
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Track test performance over time
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={timeRange}
            onChange={(e) => onTimeRangeChange?.(e.target.value as any)}
            className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm"
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
            <option value="all">All time</option>
          </select>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600 dark:text-gray-400">Current Pass Rate</span>
              {getTrendIcon(stats.trend)}
            </div>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-2">
              {stats.current.toFixed(1)}%
            </p>
            <p className={`text-xs mt-1 ${stats.trend === 'up' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              {stats.trend === 'up' ? '+' : '-'}{stats.change.toFixed(1)}% from last run
            </p>
          </div>

          <div className="p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
            <span className="text-sm text-gray-600 dark:text-gray-400">Average Pass Rate</span>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-2">
              {stats.average.toFixed(1)}%
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
              Over {trendData.length} runs
            </p>
          </div>

          <div className="p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
            <span className="text-sm text-gray-600 dark:text-gray-400">Total Tests Run</span>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-2">
              {trendData.reduce((sum, d) => sum + d.total_tests, 0)}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
              Across all cycles
            </p>
          </div>

          <div className="p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
            <span className="text-sm text-gray-600 dark:text-gray-400">Flaky Tests</span>
            <p className="text-2xl font-bold text-yellow-600 dark:text-yellow-400 mt-2">
              {flakyTests.length}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
              Need attention
            </p>
          </div>
        </div>
      )}

      {/* View Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-6">
          <button
            onClick={() => setSelectedView('overview')}
            className={`pb-3 px-1 border-b-2 font-medium text-sm transition-colors ${
              selectedView === 'overview'
                ? 'border-purple-500 text-purple-600 dark:text-purple-400'
                : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
            }`}
          >
            Overview
          </button>
          <button
            onClick={() => setSelectedView('flaky')}
            className={`pb-3 px-1 border-b-2 font-medium text-sm transition-colors ${
              selectedView === 'flaky'
                ? 'border-purple-500 text-purple-600 dark:text-purple-400'
                : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
            }`}
          >
            Flaky Tests ({flakyTests.length})
          </button>
          <button
            onClick={() => setSelectedView('patterns')}
            className={`pb-3 px-1 border-b-2 font-medium text-sm transition-colors ${
              selectedView === 'patterns'
                ? 'border-purple-500 text-purple-600 dark:text-purple-400'
                : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
            }`}
          >
            Failure Patterns
          </button>
        </nav>
      </div>

      {/* Content */}
      {selectedView === 'overview' && (
        <div className="space-y-4">
          <div className="p-6 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg">
            <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
              Pass Rate Over Time
            </h4>
            <div className="h-64 flex items-end justify-between gap-1">
              {trendData.slice(-14).map((point, i) => {
                const height = point.pass_rate
                const isLatest = i === trendData.slice(-14).length - 1
                return (
                  <div key={point.date} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className={`w-full rounded-t transition-all ${
                        isLatest
                          ? 'bg-purple-500'
                          : height >= 90
                          ? 'bg-green-500'
                          : height >= 70
                          ? 'bg-yellow-500'
                          : 'bg-red-500'
                      }`}
                      style={{ height: `${height}%` }}
                      title={`${point.date}: ${point.pass_rate.toFixed(1)}%`}
                    />
                    {i % 3 === 0 && (
                      <span className="text-xs text-gray-600 dark:text-gray-400">
                        {new Date(point.date).toLocaleDateString('en', { month: 'short', day: 'numeric' })}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {selectedView === 'flaky' && (
        <div className="space-y-3">
          {flakyTests.map(test => (
            <div
              key={test.test_id}
              className="p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h5 className="font-medium text-gray-900 dark:text-gray-100">
                    {test.test_name}
                  </h5>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {test.passed_runs}/{test.total_runs} runs passed
                  </p>
                </div>
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${getFlakinessColor(test.flakiness_score)}`}>
                  {test.flakiness_score}% flaky
                </span>
              </div>
              {test.last_failure && (
                <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
                  Last failure: {test.last_failure}
                </p>
              )}
            </div>
          ))}
          {flakyTests.length === 0 && (
            <div className="text-center py-8 text-gray-500 dark:text-gray-500">
              No flaky tests detected! 🎉
            </div>
          )}
        </div>
      )}

      {selectedView === 'patterns' && (
        <div className="space-y-3">
          {failurePatterns.map(pattern => (
            <div
              key={pattern.category}
              className="p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h5 className="font-medium text-gray-900 dark:text-gray-100">
                    {pattern.category}
                  </h5>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      {pattern.count} occurrences
                    </span>
                    <span className="flex items-center gap-1">
                      {getPatternTrendIcon(pattern.trend)}
                      <span className="text-xs capitalize">{pattern.trend}</span>
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="flex flex-col gap-1 items-end">
                    {pattern.examples.slice(0, 2).map((example, i) => (
                      <span key={i} className="text-xs text-gray-600 dark:text-gray-400">
                        {example}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default UATHistoricalTrends
