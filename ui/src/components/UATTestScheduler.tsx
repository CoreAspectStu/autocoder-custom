/**
 * UAT Test Scheduler Component
 *
 * Provides UI for scheduling automated UAT test runs.
 * Supports cron-based scheduling and one-time scheduled runs.
 */

import { useState } from 'react'
import {
  Calendar,
  Clock,
  Play,
  Plus,
  Trash2,
  Save,
  Bell
} from 'lucide-react'

export type ScheduleFrequency = 'once' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'cron'

export interface ScheduleConfig {
  id: string
  name: string
  frequency: ScheduleFrequency
  cron_expression?: string
  timezone: string
  enabled: boolean
  next_run: string
  last_run?: string
  journeys: string[]
  notify_on_failure: boolean
  notify_email?: string
}

interface UATTestSchedulerProps {
  projectId: string
  onSchedule?: (config: ScheduleConfig) => void
}

const FREQUENCY_OPTIONS = [
  { value: 'once', label: 'Run Once', description: 'Schedule a single test run' },
  { value: 'hourly', label: 'Hourly', description: 'Run every hour' },
  { value: 'daily', label: 'Daily', description: 'Run once per day' },
  { value: 'weekly', label: 'Weekly', description: 'Run once per week' },
  { value: 'monthly', label: 'Monthly', description: 'Run once per month' },
  { value: 'cron', label: 'Custom (Cron)', description: 'Use custom cron expression' }
]

export function UATTestScheduler({ projectId, onSchedule }: UATTestSchedulerProps) {
  const [schedules, setSchedules] = useState<ScheduleConfig[]>([])
  const [showForm, setShowForm] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState<ScheduleConfig | null>(null)

  const [formData, setFormData] = useState({
    name: '',
    frequency: 'daily' as ScheduleFrequency,
    cron_expression: '',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    enabled: true,
    journeys: [] as string[],
    notify_on_failure: true,
    notify_email: ''
  })

  const handleSave = () => {
    const config: ScheduleConfig = {
      id: editingSchedule?.id || `schedule-${Date.now()}`,
      name: formData.name,
      frequency: formData.frequency,
      cron_expression: formData.cron_expression || undefined,
      timezone: formData.timezone,
      enabled: formData.enabled,
      next_run: calculateNextRun(formData.frequency, formData.cron_expression),
      last_run: editingSchedule?.last_run,
      journeys: formData.journeys,
      notify_on_failure: formData.notify_on_failure,
      notify_email: formData.notify_email || undefined
    }

    if (editingSchedule) {
      setSchedules(prev => prev.map(s => s.id === editingSchedule.id ? config : s))
    } else {
      setSchedules(prev => [...prev, config])
    }

    onSchedule?.(config)
    setShowForm(false)
    setEditingSchedule(null)
    resetForm()
  }

  const handleDelete = (id: string) => {
    setSchedules(prev => prev.filter(s => s.id !== id))
  }

  const handleEdit = (schedule: ScheduleConfig) => {
    setEditingSchedule(schedule)
    setFormData({
      name: schedule.name,
      frequency: schedule.frequency,
      cron_expression: schedule.cron_expression || '',
      timezone: schedule.timezone,
      enabled: schedule.enabled,
      journeys: schedule.journeys,
      notify_on_failure: schedule.notify_on_failure,
      notify_email: schedule.notify_email || ''
    })
    setShowForm(true)
  }

  const resetForm = () => {
    setFormData({
      name: '',
      frequency: 'daily',
      cron_expression: '',
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      enabled: true,
      journeys: [],
      notify_on_failure: true,
      notify_email: ''
    })
  }

  const calculateNextRun = (frequency: ScheduleFrequency, cron?: string): string => {
    // Simplified next run calculation
    const now = new Date()
    switch (frequency) {
      case 'hourly':
        now.setHours(now.getHours() + 1)
        break
      case 'daily':
        now.setDate(now.getDate() + 1)
        now.setHours(9, 0, 0, 0)
        break
      case 'weekly':
        now.setDate(now.getDate() + 7)
        break
      case 'monthly':
        now.setMonth(now.getMonth() + 1)
        break
      default:
        now.setHours(now.getHours() + 1)
    }
    return now.toISOString()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Test Schedules
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Configure automated test runs for your project
          </p>
        </div>
        <button
          onClick={() => { setShowForm(true); resetForm(); }}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Schedule
        </button>
      </div>

      {/* Schedules List */}
      {schedules.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <Calendar className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-400">No schedules configured</p>
          <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">
            Create a schedule to automate your test runs
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {schedules.map(schedule => (
            <div
              key={schedule.id}
              className={`p-4 border-2 rounded-lg transition-all ${
                schedule.enabled
                  ? 'border-gray-200 dark:border-gray-700'
                  : 'border-gray-100 dark:border-gray-800 opacity-60'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                      {schedule.name}
                    </h4>
                    <span className={`px-2 py-0.5 text-xs rounded-full ${
                      schedule.enabled
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
                    }`}>
                      {schedule.enabled ? 'Active' : 'Paused'}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-sm text-gray-600 dark:text-gray-400">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {schedule.frequency}
                    </span>
                    <span>{schedule.timezone}</span>
                    {schedule.notify_on_failure && (
                      <span className="flex items-center gap-1">
                        <Bell className="w-3 h-3" />
                        Notifications enabled
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                    Next run: {new Date(schedule.next_run).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleEdit(schedule)}
                    className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
                    title="Edit schedule"
                  >
                    ✏️
                  </button>
                  <button
                    onClick={() => handleDelete(schedule.id)}
                    className="p-2 hover:bg-red-100 dark:hover:bg-red-900/20 rounded transition-colors"
                    title="Delete schedule"
                  >
                    <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Schedule Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-lg w-full">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {editingSchedule ? 'Edit Schedule' : 'New Schedule'}
              </h3>
            </div>

            <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Schedule Name
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., Daily Smoke Tests"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Frequency
                </label>
                <select
                  value={formData.frequency}
                  onChange={(e) => setFormData({ ...formData, frequency: e.target.value as ScheduleFrequency })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                >
                  {FREQUENCY_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {formData.frequency === 'cron' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Cron Expression
                  </label>
                  <input
                    type="text"
                    value={formData.cron_expression}
                    onChange={(e) => setFormData({ ...formData, cron_expression: e.target.value })}
                    placeholder="0 9 * * *"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 font-mono text-sm"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                    Standard cron format: minute hour day month weekday
                  </p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Timezone
                </label>
                <input
                  type="text"
                  value={formData.timezone}
                  onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                />
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="notify"
                  checked={formData.notify_on_failure}
                  onChange={(e) => setFormData({ ...formData, notify_on_failure: e.target.checked })}
                  className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
                />
                <label htmlFor="notify" className="text-sm text-gray-700 dark:text-gray-300">
                  Notify on test failures
                </label>
              </div>

              {formData.notify_on_failure && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Notification Email
                  </label>
                  <input
                    type="email"
                    value={formData.notify_email}
                    onChange={(e) => setFormData({ ...formData, notify_email: e.target.value })}
                    placeholder="devops@example.com"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                  />
                </div>
              )}
            </div>

            <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
              <button
                onClick={() => { setShowForm(false); setEditingSchedule(null); }}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg flex items-center gap-2"
              >
                <Save className="w-4 h-4" />
                Save Schedule
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default UATTestScheduler
