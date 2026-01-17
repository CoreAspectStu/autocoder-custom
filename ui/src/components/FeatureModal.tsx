import { useState } from 'react'
import { X, CheckCircle2, Circle, SkipForward, Trash2, Loader2, AlertCircle, Pencil, Link2, AlertTriangle } from 'lucide-react'
import { useSkipFeature, useDeleteFeature, useFeatures } from '../hooks/useProjects'
import { EditFeatureForm } from './EditFeatureForm'
import type { Feature } from '../lib/types'

// Generate consistent color for category (matches FeatureCard pattern)
function getCategoryColor(category: string): string {
  const colors = [
    '#ff006e', // pink (accent)
    '#00b4d8', // cyan (progress)
    '#70e000', // green (done)
    '#ffd60a', // yellow (pending)
    '#ff5400', // orange (danger)
    '#8338ec', // purple
    '#3a86ff', // blue
  ]

  let hash = 0
  for (let i = 0; i < category.length; i++) {
    hash = category.charCodeAt(i) + ((hash << 5) - hash)
  }

  return colors[Math.abs(hash) % colors.length]
}

interface FeatureModalProps {
  feature: Feature
  projectName: string
  onClose: () => void
}

export function FeatureModal({ feature, projectName, onClose }: FeatureModalProps) {
  const [error, setError] = useState<string | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showEdit, setShowEdit] = useState(false)

  const skipFeature = useSkipFeature(projectName)
  const deleteFeature = useDeleteFeature(projectName)
  const { data: allFeatures } = useFeatures(projectName)

  // Build a map of feature ID to feature for looking up dependency names
  const featureMap = new Map<number, Feature>()
  if (allFeatures) {
    ;[...allFeatures.pending, ...allFeatures.in_progress, ...allFeatures.done].forEach(f => {
      featureMap.set(f.id, f)
    })
  }

  // Get dependency features
  const dependencies = (feature.dependencies || [])
    .map(id => featureMap.get(id))
    .filter((f): f is Feature => f !== undefined)

  // Get blocking dependencies (unmet dependencies)
  const blockingDeps = (feature.blocking_dependencies || [])
    .map(id => featureMap.get(id))
    .filter((f): f is Feature => f !== undefined)

  const handleSkip = async () => {
    setError(null)
    try {
      await skipFeature.mutateAsync(feature.id)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to skip feature')
    }
  }

  const handleDelete = async () => {
    setError(null)
    try {
      await deleteFeature.mutateAsync(feature.id)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete feature')
    }
  }

  // Show edit form when in edit mode
  if (showEdit) {
    return (
      <EditFeatureForm
        feature={feature}
        projectName={projectName}
        onClose={() => setShowEdit(false)}
        onSaved={onClose}
      />
    )
  }

  return (
    <div className="neo-modal-backdrop" onClick={onClose}>
      <div
        className="neo-modal w-full max-w-2xl p-0"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b-3 border-[var(--color-neo-border)]">
          <div>
            <span
              className="neo-badge mb-2"
              style={{ backgroundColor: getCategoryColor(feature.category), color: 'var(--color-neo-text-on-bright)' }}
            >
              {feature.category}
            </span>
            <h2 className="font-display text-2xl font-bold">
              {feature.name}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="neo-btn neo-btn-ghost p-2"
          >
            <X size={24} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Error Message */}
          {error && (
            <div className="flex items-center gap-3 p-4 bg-[var(--color-neo-error-bg)] text-[var(--color-neo-error-text)] border-3 border-[var(--color-neo-error-border)]">
              <AlertCircle size={20} />
              <span>{error}</span>
              <button
                onClick={() => setError(null)}
                className="ml-auto hover:opacity-70 transition-opacity"
              >
                <X size={16} />
              </button>
            </div>
          )}

          {/* Status */}
          <div className="flex items-center gap-3 p-4 bg-[var(--color-neo-bg)] border-3 border-[var(--color-neo-border)]">
            {feature.passes ? (
              <>
                <CheckCircle2 size={24} className="text-[var(--color-neo-done)]" />
                <span className="font-display font-bold text-[var(--color-neo-done)]">
                  COMPLETE
                </span>
              </>
            ) : (
              <>
                <Circle size={24} className="text-[var(--color-neo-text-secondary)]" />
                <span className="font-display font-bold text-[var(--color-neo-text-secondary)]">
                  PENDING
                </span>
              </>
            )}
            <span className="ml-auto font-mono text-sm">
              Priority: #{feature.priority}
            </span>
          </div>

          {/* Description */}
          <div>
            <h3 className="font-display font-bold mb-2 uppercase text-sm">
              Description
            </h3>
            <p className="text-[var(--color-neo-text-secondary)]">
              {feature.description}
            </p>
          </div>

          {/* Blocked By Warning */}
          {blockingDeps.length > 0 && (
            <div className="p-4 bg-[var(--color-neo-warning-bg)] border-3 border-[var(--color-neo-warning-border)]">
              <h3 className="font-display font-bold mb-2 uppercase text-sm flex items-center gap-2 text-[var(--color-neo-warning-text)]">
                <AlertTriangle size={16} />
                Blocked By
              </h3>
              <p className="text-sm text-[var(--color-neo-warning-text)] mb-2">
                This feature cannot start until the following dependencies are complete:
              </p>
              <ul className="space-y-1">
                {blockingDeps.map(dep => (
                  <li
                    key={dep.id}
                    className="flex items-center gap-2 text-sm"
                  >
                    <Circle size={14} className="text-[var(--color-neo-warning-text)]" />
                    <span className="font-mono text-xs text-[var(--color-neo-warning-text)]">#{dep.id}</span>
                    <span className="text-[var(--color-neo-warning-text)]">{dep.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Dependencies */}
          {dependencies.length > 0 && (
            <div>
              <h3 className="font-display font-bold mb-2 uppercase text-sm flex items-center gap-2">
                <Link2 size={16} />
                Depends On
              </h3>
              <ul className="space-y-1">
                {dependencies.map(dep => (
                  <li
                    key={dep.id}
                    className="flex items-center gap-2 p-2 bg-[var(--color-neo-bg)] border-2 border-[var(--color-neo-border)]"
                  >
                    {dep.passes ? (
                      <CheckCircle2 size={16} className="text-[var(--color-neo-done)]" />
                    ) : (
                      <Circle size={16} className="text-[var(--color-neo-text-secondary)]" />
                    )}
                    <span className="font-mono text-xs text-[var(--color-neo-text-secondary)]">#{dep.id}</span>
                    <span className={dep.passes ? 'text-[var(--color-neo-done)]' : ''}>{dep.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Steps */}
          {feature.steps.length > 0 && (
            <div>
              <h3 className="font-display font-bold mb-2 uppercase text-sm">
                Test Steps
              </h3>
              <ol className="list-decimal list-inside space-y-2">
                {feature.steps.map((step, index) => (
                  <li
                    key={index}
                    className="p-3 bg-[var(--color-neo-bg)] border-3 border-[var(--color-neo-border)]"
                  >
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        {/* Actions */}
        {!feature.passes && (
          <div className="p-6 border-t-3 border-[var(--color-neo-border)] bg-[var(--color-neo-bg)]">
            {showDeleteConfirm ? (
              <div className="space-y-4">
                <p className="font-bold text-center">
                  Are you sure you want to delete this feature?
                </p>
                <div className="flex gap-3">
                  <button
                    onClick={handleDelete}
                    disabled={deleteFeature.isPending}
                    className="neo-btn neo-btn-danger flex-1"
                  >
                    {deleteFeature.isPending ? (
                      <Loader2 size={18} className="animate-spin" />
                    ) : (
                      'Yes, Delete'
                    )}
                  </button>
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    disabled={deleteFeature.isPending}
                    className="neo-btn neo-btn-ghost flex-1"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-3">
                <button
                  onClick={() => setShowEdit(true)}
                  disabled={skipFeature.isPending}
                  className="neo-btn neo-btn-primary flex-1"
                >
                  <Pencil size={18} />
                  Edit
                </button>
                <button
                  onClick={handleSkip}
                  disabled={skipFeature.isPending}
                  className="neo-btn neo-btn-warning flex-1"
                >
                  {skipFeature.isPending ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <>
                      <SkipForward size={18} />
                      Skip
                    </>
                  )}
                </button>
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  disabled={skipFeature.isPending}
                  className="neo-btn neo-btn-danger"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
