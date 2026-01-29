import { useState, useId } from 'react'
import { X, Plus, Trash2, Loader2, AlertCircle } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createUATTest } from '../lib/api'

interface Step {
  id: string
  value: string
}

interface AddUATTestFormProps {
  onClose: () => void
}

export function AddUATTestForm({ onClose }: AddUATTestFormProps) {
  const formId = useId()
  const queryClient = useQueryClient()

  const [scenario, setScenario] = useState('')
  const [journey, setJourney] = useState('')
  const [phase, setPhase] = useState<'smoke' | 'functional' | 'regression' | 'uat'>('functional')
  const [steps, setSteps] = useState<Step[]>([{ id: `${formId}-step-0`, value: '' }])
  const [expectedResult, setExpectedResult] = useState('')
  const [category, setCategory] = useState('')
  const [priority, setPriority] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [stepCounter, setStepCounter] = useState(1)

  const createTestMutation = useMutation({
    mutationFn: createUATTest,
    onSuccess: (data) => {
      // Invalidate UAT tests query to refresh the kanban board
      queryClient.invalidateQueries({ queryKey: ['uat-tests'] })
      onClose()
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  const handleAddStep = () => {
    setSteps([...steps, { id: `${formId}-step-${stepCounter}`, value: '' }])
    setStepCounter(stepCounter + 1)
  }

  const handleRemoveStep = (id: string) => {
    setSteps(steps.filter(step => step.id !== id))
  }

  const handleStepChange = (id: string, value: string) => {
    setSteps(steps.map(step =>
      step.id === id ? { ...step, value } : step
    ))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    // Filter out empty steps
    const filteredSteps = steps
      .map(s => s.value.trim())
      .filter(s => s.length > 0)

    if (filteredSteps.length === 0) {
      setError('At least one test step is required')
      return
    }

    try {
      await createTestMutation.mutateAsync({
        scenario: scenario.trim(),
        journey: journey.trim(),
        phase,
        steps: filteredSteps,
        expected_result: expectedResult.trim(),
        category: category.trim() || phase,
        priority: priority ? parseInt(priority, 10) : undefined,
      })
    } catch (err) {
      // Error is handled by mutation onError
    }
  }

  const isValid = scenario.trim() && journey.trim() && phase && expectedResult.trim()

  return (
    <div className="neo-modal-backdrop" onClick={onClose}>
      <div
        className="neo-modal w-full max-w-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b-3 border-[var(--color-neo-border)]">
          <h2 className="font-display text-2xl font-bold">
            Add UAT Test
          </h2>
          <button
            onClick={onClose}
            className="neo-btn neo-btn-ghost p-2"
          >
            <X size={24} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Error Message */}
          {error && (
            <div className="flex items-center gap-3 p-4 bg-[var(--color-neo-error-bg)] text-[var(--color-neo-error-text)] border-3 border-[var(--color-neo-error-border)]">
              <AlertCircle size={20} />
              <span>{error}</span>
              <button
                type="button"
                onClick={() => setError(null)}
                className="ml-auto hover:opacity-70 transition-opacity"
              >
                <X size={16} />
              </button>
            </div>
          )}

          {/* Scenario */}
          <div>
            <label className="block font-display font-bold mb-2 uppercase text-sm">
              Test Scenario <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              placeholder="e.g., User login with valid credentials"
              className="neo-input"
              required
            />
            <p className="text-xs text-[var(--color-neo-text-secondary)] mt-1">
              A brief name describing what this test validates
            </p>
          </div>

          {/* Journey */}
          <div>
            <label className="block font-display font-bold mb-2 uppercase text-sm">
              User Journey <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={journey}
              onChange={(e) => setJourney(e.target.value)}
              placeholder="e.g., Authentication, Checkout, Profile Management"
              className="neo-input"
              required
            />
            <p className="text-xs text-[var(--color-neo-text-secondary)] mt-1">
              The user journey or feature area being tested
            </p>
          </div>

          {/* Phase */}
          <div>
            <label className="block font-display font-bold mb-2 uppercase text-sm">
              Test Phase <span className="text-red-500">*</span>
            </label>
            <select
              value={phase}
              onChange={(e) => setPhase(e.target.value as typeof phase)}
              className="neo-input"
              required
            >
              <option value="smoke">Smoke Test - Critical path verification</option>
              <option value="functional">Functional Test - Feature validation</option>
              <option value="regression">Regression Test - Workflow integrity</option>
              <option value="uat">UAT Test - End-to-end user scenario</option>
            </select>
            <p className="text-xs text-[var(--color-neo-text-secondary)] mt-1">
              The testing phase this test belongs to
            </p>
          </div>

          {/* Category & Priority Row */}
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block font-display font-bold mb-2 uppercase text-sm">
                Category (Optional)
              </label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Defaults to phase"
                className="neo-input"
              />
            </div>
            <div className="w-32">
              <label className="block font-display font-bold mb-2 uppercase text-sm">
                Priority
              </label>
              <input
                type="number"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                placeholder="Auto"
                min="1"
                className="neo-input"
              />
            </div>
          </div>

          {/* Steps */}
          <div>
            <label className="block font-display font-bold mb-2 uppercase text-sm">
              Test Steps <span className="text-red-500">*</span>
            </label>
            <div className="space-y-2">
              {steps.map((step, index) => (
                <div key={step.id} className="flex gap-2 items-center">
                  <span
                    className="w-10 h-10 flex-shrink-0 flex items-center justify-center font-mono font-bold text-sm border-3 border-[var(--color-neo-border)] bg-[var(--color-neo-bg)] text-[var(--color-neo-text-secondary)]"
                    style={{ boxShadow: 'var(--shadow-neo-sm)' }}
                  >
                    {index + 1}
                  </span>
                  <input
                    type="text"
                    value={step.value}
                    onChange={(e) => handleStepChange(step.id, e.target.value)}
                    placeholder="Describe this step..."
                    className="neo-input flex-1"
                  />
                  {steps.length > 1 && (
                    <button
                      type="button"
                      onClick={() => handleRemoveStep(step.id)}
                      className="neo-btn neo-btn-ghost p-2"
                    >
                      <Trash2 size={18} />
                    </button>
                  )}
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={handleAddStep}
              className="neo-btn neo-btn-ghost mt-2 text-sm"
            >
              <Plus size={16} />
              Add Step
            </button>
          </div>

          {/* Expected Result */}
          <div>
            <label className="block font-display font-bold mb-2 uppercase text-sm">
              Expected Result <span className="text-red-500">*</span>
            </label>
            <textarea
              value={expectedResult}
              onChange={(e) => setExpectedResult(e.target.value)}
              placeholder="Describe what should happen when the test passes..."
              className="neo-input min-h-[80px] resize-y"
              required
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4 border-t-3 border-[var(--color-neo-border)]">
            <button
              type="submit"
              disabled={!isValid || createTestMutation.isPending}
              className="neo-btn neo-btn-success flex-1"
            >
              {createTestMutation.isPending ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <>
                  <Plus size={18} />
                  Create UAT Test
                </>
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="neo-btn neo-btn-ghost"
              disabled={createTestMutation.isPending}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
