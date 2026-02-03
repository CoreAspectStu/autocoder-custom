/**
 * UAT Custom Metrics Component
 *
 * Allows users to define and track custom test metrics.
 * Supports custom calculations, aggregations, and alerts.
 */

import { useState } from 'react'
import {
  Plus,
  Trash2,
  Edit,
  Save,
  TrendingUp,
  Calculator,
  Bell
} from 'lucide-react'

export type MetricType = 'count' | 'percentage' | 'average' | 'sum' | 'custom'

export interface CustomMetric {
  id: string
  name: string
  description: string
  type: MetricType
  formula?: string
  query?: string
  threshold?: {
    operator: 'gt' | 'lt' | 'eq' | 'gte' | 'lte'
    value: number
    alert: boolean
  }
  tags: string[]
  enabled: boolean
}

interface UATCustomMetricsProps {
  projectId: string
  onMetricCreate?: (metric: CustomMetric) => void
  onMetricUpdate?: (metric: CustomMetric) => void
}

const METRIC_TYPES = [
  { value: 'count', label: 'Count', description: 'Count occurrences matching criteria' },
  { value: 'percentage', label: 'Percentage', description: 'Calculate percentage of total' },
  { value: 'average', label: 'Average', description: 'Average of numeric values' },
  { value: 'sum', label: 'Sum', description: 'Sum of values' },
  { value: 'custom', label: 'Custom Formula', description: 'Define a custom calculation' }
]

export function UATCustomMetrics({ projectId, onMetricCreate, onMetricUpdate }: UATCustomMetricsProps) {
  const [metrics, setMetrics] = useState<CustomMetric[]>([
    {
      id: 'metric-1',
      name: 'API Response Time',
      description: 'Average API response time across all tests',
      type: 'average',
      query: 'test_type:api',
      threshold: { operator: 'lte', value: 500, alert: true },
      tags: ['performance', 'api'],
      enabled: true
    }
  ])

  const [showForm, setShowForm] = useState(false)
  const [editingMetric, setEditingMetric] = useState<CustomMetric | null>(null)

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    type: 'count' as MetricType,
    formula: '',
    query: '',
    threshold_operator: 'gt' as 'gt' | 'lt' | 'eq' | 'gte' | 'lte',
    threshold_value: '',
    threshold_alert: false,
    tags: [] as string[]
  })

  const handleSave = () => {
    const metric: CustomMetric = {
      id: editingMetric?.id || `metric-${Date.now()}`,
      name: formData.name,
      description: formData.description,
      type: formData.type,
      formula: formData.type === 'custom' ? formData.formula : undefined,
      query: formData.query || undefined,
      threshold: formData.threshold_value ? {
        operator: formData.threshold_operator,
        value: parseFloat(formData.threshold_value),
        alert: formData.threshold_alert
      } : undefined,
      tags: formData.tags,
      enabled: true
    }

    if (editingMetric) {
      setMetrics(prev => prev.map(m => m.id === editingMetric.id ? metric : m))
      onMetricUpdate?.(metric)
    } else {
      setMetrics(prev => [...prev, metric])
      onMetricCreate?.(metric)
    }

    setShowForm(false)
    setEditingMetric(null)
    resetForm()
  }

  const handleDelete = (id: string) => {
    setMetrics(prev => prev.filter(m => m.id !== id))
  }

  const handleEdit = (metric: CustomMetric) => {
    setEditingMetric(metric)
    setFormData({
      name: metric.name,
      description: metric.description,
      type: metric.type,
      formula: metric.formula || '',
      query: metric.query || '',
      threshold_operator: metric.threshold?.operator || 'gt',
      threshold_value: metric.threshold?.value.toString() || '',
      threshold_alert: metric.threshold?.alert || false,
      tags: metric.tags
    })
    setShowForm(true)
  }

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      type: 'count',
      formula: '',
      query: '',
      threshold_operator: 'gt',
      threshold_value: '',
      threshold_alert: false,
      tags: []
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Custom Metrics
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Define and track custom test metrics
          </p>
        </div>
        <button
          onClick={() => { setShowForm(true); resetForm(); }}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Metric
        </button>
      </div>

      {/* Metrics List */}
      {metrics.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <Calculator className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-400">No custom metrics defined</p>
          <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">
            Create metrics to track specific KPIs
          </p>
        </div>
      ) : (
        <div className="grid gap-4">
          {metrics.map(metric => (
            <div
              key={metric.id}
              className={`p-4 border-2 rounded-lg transition-all ${
                metric.enabled
                  ? 'border-gray-200 dark:border-gray-700'
                  : 'border-gray-100 dark:border-gray-800 opacity-60'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                      {metric.name}
                    </h4>
                    <span className="px-2 py-0.5 text-xs rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">
                      {metric.type}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {metric.description}
                  </p>
                  {metric.query && (
                    <code className="block mt-2 text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">
                      {metric.query}
                    </code>
                  )}
                  {metric.threshold && (
                    <div className="flex items-center gap-2 mt-2 text-sm">
                      <Bell className="w-3 h-3 text-gray-500" />
                      <span className="text-gray-600 dark:text-gray-400">
                        Alert when {metric.threshold.operator} {metric.threshold.value}
                      </span>
                    </div>
                  )}
                  {metric.tags.length > 0 && (
                    <div className="flex items-center gap-2 mt-2">
                      {metric.tags.map(tag => (
                        <span
                          key={tag}
                          className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleEdit(metric)}
                    className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
                    title="Edit metric"
                  >
                    <Edit className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  </button>
                  <button
                    onClick={() => handleDelete(metric.id)}
                    className="p-2 hover:bg-red-100 dark:hover:bg-red-900/20 rounded transition-colors"
                    title="Delete metric"
                  >
                    <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Metric Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-lg w-full">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {editingMetric ? 'Edit Metric' : 'New Metric'}
              </h3>
            </div>

            <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Metric Name
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., API Response Time"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Description
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="What does this metric measure?"
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Metric Type
                </label>
                <select
                  value={formData.type}
                  onChange={(e) => setFormData({ ...formData, type: e.target.value as MetricType })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                >
                  {METRIC_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Query / Filter (optional)
                </label>
                <input
                  type="text"
                  value={formData.query}
                  onChange={(e) => setFormData({ ...formData, query: e.target.value })}
                  placeholder="e.g., test_type:api"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 font-mono text-sm"
                />
              </div>

              {formData.type === 'custom' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Custom Formula
                  </label>
                  <input
                    type="text"
                    value={formData.formula}
                    onChange={(e) => setFormData({ ...formData, formula: e.target.value })}
                    placeholder="e.g., (passed / total) * 100"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 font-mono text-sm"
                  />
                </div>
              )}

              <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Alert Threshold (optional)
                </label>
                <div className="flex items-center gap-2">
                  <select
                    value={formData.threshold_operator}
                    onChange={(e) => setFormData({ ...formData, threshold_operator: e.target.value as any })}
                    className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                  >
                    <option value="gt">Greater than</option>
                    <option value="gte">Greater or equal</option>
                    <option value="lt">Less than</option>
                    <option value="lte">Less or equal</option>
                    <option value="eq">Equal to</option>
                  </select>
                  <input
                    type="number"
                    value={formData.threshold_value}
                    onChange={(e) => setFormData({ ...formData, threshold_value: e.target.value })}
                    placeholder="Value"
                    className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                  />
                  <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <input
                      type="checkbox"
                      checked={formData.threshold_alert}
                      onChange={(e) => setFormData({ ...formData, threshold_alert: e.target.checked })}
                      className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
                    />
                    Alert
                  </label>
                </div>
              </div>
            </div>

            <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
              <button
                onClick={() => { setShowForm(false); setEditingMetric(null); }}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg flex items-center gap-2"
              >
                <Save className="w-4 h-4" />
                Save Metric
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default UATCustomMetrics
