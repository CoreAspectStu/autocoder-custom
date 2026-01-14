import { useState, useId } from 'react'
import { X, Save, Plus, Trash2, Loader2, AlertCircle } from 'lucide-react'
import { useUpdateFeature } from '../hooks/useProjects'
import type { Feature } from '../lib/types'

interface Step {
  id: string
  value: string
}

interface EditFeatureFormProps {
  feature: Feature
  projectName: string
  onClose: () => void
  onSaved: () => void
}

export function EditFeatureForm({ feature, projectName, onClose, onSaved }: EditFeatureFormProps) {
  const formId = useId()
  const [category, setCategory] = useState(feature.category)
  const [name, setName] = useState(feature.name)
  const [description, setDescription] = useState(feature.description)
  const [priority, setPriority] = useState(String(feature.priority))
  const [steps, setSteps] = useState<Step[]>(() =>
    feature.steps.length > 0
      ? feature.steps.map((step, i) => ({ id: `${formId}-step-${i}`, value: step }))
      : [{ id: `${formId}-step-0`, value: '' }]
  )
  const [error, setError] = useState<string | null>(null)
  const [stepCounter, setStepCounter] = useState(feature.steps.length || 1)

  const updateFeature = useUpdateFeature(projectName)

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

    const filteredSteps = steps
      .map(s => s.value.trim())
      .filter(s => s.length > 0)

    try {
      await updateFeature.mutateAsync({
        featureId: feature.id,
        update: {
          category: category.trim(),
          name: name.trim(),
          description: description.trim(),
          steps: filteredSteps,
          priority: parseInt(priority, 10),
        },
      })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update feature')
    }
  }

  const isValid = category.trim() && name.trim() && description.trim()

  // Check if any changes were made
  const currentSteps = steps.map(s => s.value.trim()).filter(s => s)
  const hasChanges =
    category.trim() !== feature.category ||
    name.trim() !== feature.name ||
    description.trim() !== feature.description ||
    parseInt(priority, 10) !== feature.priority ||
    JSON.stringify(currentSteps) !== JSON.stringify(feature.steps)

  return (
    <div className="neo-modal-backdrop" onClick={onClose}>
      <div
        className="neo-modal w-full max-w-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b-3 border-[var(--color-neo-border)]">
          <h2 className="font-display text-2xl font-bold">
            Edit Feature
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
            <div className="flex items-center gap-3 p-4 bg-[var(--color-neo-danger)] text-white border-3 border-[var(--color-neo-border)]">
              <AlertCircle size={20} />
              <span>{error}</span>
              <button
                type="button"
                onClick={() => setError(null)}
                className="ml-auto"
              >
                <X size={16} />
              </button>
            </div>
          )}

          {/* Category & Priority Row */}
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block font-display font-bold mb-2 uppercase text-sm">
                Category
              </label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="e.g., Authentication, UI, API"
                className="neo-input"
                required
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
                min="1"
                className="neo-input"
                required
              />
            </div>
          </div>

          {/* Name */}
          <div>
            <label className="block font-display font-bold mb-2 uppercase text-sm">
              Feature Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., User login form"
              className="neo-input"
              required
            />
          </div>

          {/* Description */}
          <div>
            <label className="block font-display font-bold mb-2 uppercase text-sm">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what this feature should do..."
              className="neo-input min-h-[100px] resize-y"
              required
            />
          </div>

          {/* Steps */}
          <div>
            <label className="block font-display font-bold mb-2 uppercase text-sm">
              Test Steps
            </label>
            <div className="space-y-2">
              {steps.map((step, index) => (
                <div key={step.id} className="flex gap-2">
                  <span className="neo-input w-12 text-center flex-shrink-0 flex items-center justify-center">
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

          {/* Actions */}
          <div className="flex gap-3 pt-4 border-t-3 border-[var(--color-neo-border)]">
            <button
              type="submit"
              disabled={!isValid || !hasChanges || updateFeature.isPending}
              className="neo-btn neo-btn-success flex-1"
            >
              {updateFeature.isPending ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <>
                  <Save size={18} />
                  Save Changes
                </>
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="neo-btn neo-btn-ghost"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
