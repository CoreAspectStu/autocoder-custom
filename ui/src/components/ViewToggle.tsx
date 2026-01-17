import { LayoutGrid, GitBranch } from 'lucide-react'

export type ViewMode = 'kanban' | 'graph'

interface ViewToggleProps {
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
}

/**
 * Toggle button to switch between Kanban and Graph views
 */
export function ViewToggle({ viewMode, onViewModeChange }: ViewToggleProps) {
  return (
    <div className="inline-flex rounded-lg border-2 border-neo-border p-1 bg-white shadow-neo-sm">
      <button
        onClick={() => onViewModeChange('kanban')}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium text-sm transition-all
          ${viewMode === 'kanban'
            ? 'bg-neo-accent text-white shadow-neo-sm'
            : 'text-neo-text hover:bg-neo-neutral-100'
          }
        `}
        title="Kanban View"
      >
        <LayoutGrid size={16} />
        <span>Kanban</span>
      </button>
      <button
        onClick={() => onViewModeChange('graph')}
        className={`
          flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium text-sm transition-all
          ${viewMode === 'graph'
            ? 'bg-neo-accent text-white shadow-neo-sm'
            : 'text-neo-text hover:bg-neo-neutral-100'
          }
        `}
        title="Dependency Graph View"
      >
        <GitBranch size={16} />
        <span>Graph</span>
      </button>
    </div>
  )
}
