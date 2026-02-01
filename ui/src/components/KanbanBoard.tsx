import { KanbanColumn } from './KanbanColumn'
import type { Feature, FeatureListResponse, ActiveAgent } from '../lib/types'

interface KanbanBoardProps {
  features: FeatureListResponse | undefined
  onFeatureClick: (feature: Feature) => void
  onAddFeature?: () => void
  onExpandProject?: () => void
  activeAgents?: ActiveAgent[]
  onCreateSpec?: () => void  // Callback to start spec creation
  hasSpec?: boolean          // Whether the project has a spec
  isUATMode?: boolean        // Whether UAT Mode is active
}

export function KanbanBoard({ features, onFeatureClick, onAddFeature, onExpandProject, activeAgents = [], onCreateSpec, hasSpec = true, isUATMode = false }: KanbanBoardProps) {
  // Defensive checks to prevent crashes when API returns undefined or malformed data
  // This can happen when UAT mode is toggled but the UAT API endpoint doesn't exist yet
  const safePending = features?.pending ?? []
  const safeInProgress = features?.in_progress ?? []
  const safeDone = features?.done ?? []

  const hasFeatures = (safePending.length + safeInProgress.length + safeDone.length) > 0

  // Combine all features for dependency status calculation
  const allFeatures = features
    ? [...safePending, ...safeInProgress, ...safeDone]
    : []

  if (!features) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {['Pending', 'In Progress', 'Done'].map(title => (
          <div key={title} className="neo-card p-4">
            <div className="h-8 bg-[var(--color-neo-bg)] animate-pulse mb-4" />
            <div className="space-y-3">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-24 bg-[var(--color-neo-bg)] animate-pulse" />
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <KanbanColumn
        title="Pending"
        count={safePending.length}
        features={safePending}
        allFeatures={allFeatures}
        activeAgents={activeAgents}
        color="pending"
        onFeatureClick={onFeatureClick}
        onAddFeature={onAddFeature}
        onExpandProject={onExpandProject}
        showExpandButton={hasFeatures}
        onCreateSpec={onCreateSpec}
        showCreateSpec={!hasSpec && !hasFeatures}
        isUATMode={isUATMode}
      />
      <KanbanColumn
        title="In Progress"
        count={safeInProgress.length}
        features={safeInProgress}
        allFeatures={allFeatures}
        activeAgents={activeAgents}
        color="progress"
        onFeatureClick={onFeatureClick}
      />
      <KanbanColumn
        title="Done"
        count={safeDone.length}
        features={safeDone}
        allFeatures={allFeatures}
        activeAgents={activeAgents}
        color="done"
        onFeatureClick={onFeatureClick}
      />
    </div>
  )
}
