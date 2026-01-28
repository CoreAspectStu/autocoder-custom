import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { X, Play, Filter, CheckCircle } from 'lucide-react'

interface JourneyType {
  value: string
  label: string
  description: string
}

interface ScenarioType {
  value: string
  label: string
  description: string
}

interface PresetTest {
  id: string
  label: string
  description: string
  journey_types: string[] | null
  scenario_types: string[] | null
}

interface TestOptions {
  journey_types: JourneyType[]
  scenario_types: ScenarioType[]
  preset_tests: PresetTest[]
}

interface UATTriggerModalProps {
  project: string
  onClose: () => void
  onSuccess?: (cycleId: string) => void
}

export function UATTriggerModal({ project, onClose, onSuccess }: UATTriggerModalProps) {
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null)
  const [selectedJourneyTypes, setSelectedJourneyTypes] = useState<string[]>([])
  const [selectedScenarioTypes, setSelectedScenarioTypes] = useState<string[]>([])
  const [force, setForce] = useState(false)
  const [triggerSuccess, setTriggerSuccess] = useState(false)
  const [cycleId, setCycleId] = useState<string | null>(null)

  // Fetch test options
  const { data: testOptions, isLoading } = useQuery<TestOptions>({
    queryKey: ['uat', 'test-options'],
    queryFn: async () => {
      const res = await fetch('/api/uat/test-options')
      if (!res.ok) throw new Error('Failed to fetch test options')
      return res.json()
    },
  })

  // Trigger mutation
  const triggerMutation = useMutation({
    mutationFn: async (config: any) => {
      const payload = {
        project_name: project,
        ...config
      }
      console.log('[UATTrigger] Fetching /api/uat/trigger with payload:', payload)

      const res = await fetch('/api/uat/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      console.log('[UATTrigger] Response status:', res.status, res.statusText)
      console.log('[UATTrigger] Response headers:', Object.fromEntries(res.headers.entries()))

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: res.statusText }))
        console.error('[UATTrigger] Error response:', errorData)
        throw new Error(errorData.detail || `Failed to trigger UAT: ${res.statusText}`)
      }

      const data = await res.json()
      console.log('[UATTrigger] Success response:', data)
      return data
    },
    onSuccess: (data) => {
      console.log('[UATTrigger] Mutation success:', data)
      setCycleId(data.cycle_id)
      setTriggerSuccess(true)
      onSuccess?.(data.cycle_id)
      // Close after showing success
      setTimeout(() => {
        onClose()
      }, 2000)
    },
    onError: (error: Error) => {
      console.error('[UATTrigger] Mutation error:', error)
      alert(`Error: ${error.message}`)
    },
  })

  const handlePresetSelect = (preset: PresetTest) => {
    setSelectedPreset(preset.id)
    setSelectedJourneyTypes(preset.journey_types || [])
    setSelectedScenarioTypes(preset.scenario_types || [])
  }

  const toggleJourneyType = (value: string) => {
    setSelectedPreset(null)
    setSelectedJourneyTypes(prev =>
      prev.includes(value)
        ? prev.filter(v => v !== value)
        : [...prev, value]
    )
  }

  const toggleScenarioType = (value: string) => {
    setSelectedPreset(null)
    setSelectedScenarioTypes(prev =>
      prev.includes(value)
        ? prev.filter(v => v !== value)
        : [...prev, value]
    )
  }

  const handleRunTests = () => {
    console.log('[UATTrigger] Triggering tests for project:', project)
    console.log('[UATTrigger] Config:', { force, selectedJourneyTypes, selectedScenarioTypes })

    const config: any = { force }
    if (selectedJourneyTypes.length > 0) config.journey_types = selectedJourneyTypes
    if (selectedScenarioTypes.length > 0) config.scenario_types = selectedScenarioTypes

    console.log('[UATTrigger] Final config being sent:', config)
    triggerMutation.mutate(config)
  }

  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6">Loading...</div>
      </div>
    )
  }

  if (triggerSuccess) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg max-w-md w-full p-8 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-green-100 flex items-center justify-center">
            <CheckCircle className="w-8 h-8 text-green-600" />
          </div>
          <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
            UAT Tests Started!
          </h3>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Test cycle ID: <code className="text-sm bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">{cycleId}</code>
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-500">
            The dashboard will show progress once tests begin running.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Play className="w-5 h-5 text-purple-600" />
              Run UAT Tests
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Project: {project}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Preset Tests */}
          <div>
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <Filter className="w-4 h-4" />
              Quick Presets
            </h3>
            <div className="grid grid-cols-2 gap-2">
              {(testOptions?.preset_tests || []).map((preset) => (
                <button
                  key={preset.id}
                  onClick={() => handlePresetSelect(preset)}
                  className={`p-3 text-left rounded border-2 transition-all ${
                    selectedPreset === preset.id
                      ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-purple-300'
                  }`}
                >
                  <div className="font-medium text-sm text-gray-900 dark:text-white">
                    {preset.label}
                  </div>
                  <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                    {preset.description}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Journey Types */}
          <div>
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
              Journey Types
            </h3>
            <div className="grid grid-cols-2 gap-2">
              {(testOptions?.journey_types || []).map((type) => (
                <button
                  key={type.value}
                  onClick={() => toggleJourneyType(type.value)}
                  className={`p-3 text-left rounded border-2 transition-all ${
                    selectedJourneyTypes.includes(type.value)
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-blue-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm text-gray-900 dark:text-white">
                      {type.label}
                    </span>
                    {selectedJourneyTypes.includes(type.value) && (
                      <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                  <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                    {type.description}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Scenario Types */}
          <div>
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
              Scenario Types
            </h3>
            <div className="flex gap-2">
              {(testOptions?.scenario_types || []).map((type) => (
                <button
                  key={type.value}
                  onClick={() => toggleScenarioType(type.value)}
                  className={`flex-1 p-3 text-center rounded border-2 transition-all ${
                    selectedScenarioTypes.includes(type.value)
                      ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-green-300'
                  }`}
                >
                  <div className="font-medium text-sm text-gray-900 dark:text-white">
                    {type.label}
                  </div>
                  <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                    {type.description}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Options */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="force"
              checked={force}
              onChange={(e) => setForce(e.target.checked)}
              className="rounded"
            />
            <label htmlFor="force" className="text-sm text-gray-700 dark:text-gray-300">
              Skip prerequisite checks (force run)
            </label>
          </div>

          {/* Summary */}
          {selectedJourneyTypes.length > 0 || selectedScenarioTypes.length > 0 ? (
            <div className="bg-gray-50 dark:bg-gray-700 rounded p-3 text-sm">
              <div className="font-medium text-gray-900 dark:text-white mb-1">Test Configuration:</div>
              <div className="text-gray-600 dark:text-gray-400">
                {selectedJourneyTypes.length > 0 && (
                  <span>Journeys: <strong>{selectedJourneyTypes.join(', ')}</strong></span>
                )}
                {selectedJourneyTypes.length > 0 && selectedScenarioTypes.length > 0 && ' | '}
                {selectedScenarioTypes.length > 0 && (
                  <span>Scenarios: <strong>{selectedScenarioTypes.join(', ')}</strong></span>
                )}
                {selectedJourneyTypes.length === 0 && selectedScenarioTypes.length === 0 && (
                  <span className="italic">All tests will run</span>
                )}
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 dark:bg-gray-700 rounded p-3 text-sm text-gray-600 dark:text-gray-400 italic">
              No filters selected - all tests will run
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 p-6 border-t dark:border-gray-700">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            onClick={handleRunTests}
            disabled={triggerMutation.isPending}
            className="flex-1 px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <Play className="w-4 h-4" />
            {triggerMutation.isPending ? 'Starting...' : 'Run Tests'}
          </button>
        </div>
      </div>
    </div>
  )
}
