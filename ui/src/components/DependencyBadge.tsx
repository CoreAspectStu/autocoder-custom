import { AlertTriangle, GitBranch, Check } from 'lucide-react'
import type { Feature } from '../lib/types'

interface DependencyBadgeProps {
  feature: Feature
  allFeatures?: Feature[]
  compact?: boolean
}

/**
 * Badge component showing dependency status for a feature.
 * Shows:
 * - Blocked status with count of blocking dependencies
 * - Dependency count for features with satisfied dependencies
 * - Nothing if feature has no dependencies
 */
export function DependencyBadge({ feature, allFeatures = [], compact = false }: DependencyBadgeProps) {
  const dependencies = feature.dependencies || []

  if (dependencies.length === 0) {
    return null
  }

  // Use API-computed blocked status if available, otherwise compute locally
  const isBlocked = feature.blocked ??
    (feature.blocking_dependencies && feature.blocking_dependencies.length > 0) ??
    false

  const blockingCount = feature.blocking_dependencies?.length ?? 0

  // Compute satisfied count from allFeatures if available
  let satisfiedCount = dependencies.length - blockingCount
  if (allFeatures.length > 0 && !feature.blocking_dependencies) {
    const passingIds = new Set(allFeatures.filter(f => f.passes).map(f => f.id))
    satisfiedCount = dependencies.filter(d => passingIds.has(d)).length
  }

  if (compact) {
    // Compact view for card displays
    return (
      <div
        className={`
          inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-mono
          ${isBlocked
            ? 'bg-neo-danger/20 text-neo-danger'
            : 'bg-neo-neutral-200 text-neo-text-secondary'
          }
        `}
        title={isBlocked
          ? `Blocked by ${blockingCount} ${blockingCount === 1 ? 'dependency' : 'dependencies'}`
          : `${satisfiedCount}/${dependencies.length} dependencies satisfied`
        }
      >
        {isBlocked ? (
          <>
            <AlertTriangle size={12} />
            <span>{blockingCount}</span>
          </>
        ) : (
          <>
            <GitBranch size={12} />
            <span>{satisfiedCount}/{dependencies.length}</span>
          </>
        )}
      </div>
    )
  }

  // Full view with more details
  return (
    <div className="flex items-center gap-2">
      {isBlocked ? (
        <div className="flex items-center gap-1.5 text-sm text-neo-danger">
          <AlertTriangle size={14} />
          <span className="font-medium">
            Blocked by {blockingCount} {blockingCount === 1 ? 'dependency' : 'dependencies'}
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-sm text-neo-text-secondary">
          <Check size={14} className="text-neo-done" />
          <span>
            All {dependencies.length} {dependencies.length === 1 ? 'dependency' : 'dependencies'} satisfied
          </span>
        </div>
      )}
    </div>
  )
}

/**
 * Small inline indicator for dependency status
 */
export function DependencyIndicator({ feature }: { feature: Feature }) {
  const dependencies = feature.dependencies || []
  const isBlocked = feature.blocked || (feature.blocking_dependencies && feature.blocking_dependencies.length > 0)

  if (dependencies.length === 0) {
    return null
  }

  if (isBlocked) {
    return (
      <span
        className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-neo-danger/20 text-neo-danger"
        title={`Blocked by ${feature.blocking_dependencies?.length || 0} dependencies`}
      >
        <AlertTriangle size={12} />
      </span>
    )
  }

  return (
    <span
      className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-neo-neutral-200 text-neo-text-secondary"
      title={`${dependencies.length} dependencies (all satisfied)`}
    >
      <GitBranch size={12} />
    </span>
  )
}
