import { CheckCircle2, Circle, Loader2, MessageCircle } from 'lucide-react'
import type { Feature, ActiveAgent } from '../lib/types'
import { DependencyBadge } from './DependencyBadge'
import { AgentAvatar } from './AgentAvatar'

interface FeatureCardProps {
  feature: Feature
  onClick: () => void
  isInProgress?: boolean
  allFeatures?: Feature[]
  activeAgent?: ActiveAgent // Agent working on this feature
}

// Generate consistent color for category using CSS variable references
// These map to the --color-neo-category-* variables defined in globals.css
function getCategoryColor(category: string): string {
  const colors = [
    'var(--color-neo-category-pink)',
    'var(--color-neo-category-cyan)',
    'var(--color-neo-category-green)',
    'var(--color-neo-category-yellow)',
    'var(--color-neo-category-orange)',
    'var(--color-neo-category-purple)',
    'var(--color-neo-category-blue)',
  ]

  let hash = 0
  for (let i = 0; i < category.length; i++) {
    hash = category.charCodeAt(i) + ((hash << 5) - hash)
  }

  return colors[Math.abs(hash) % colors.length]
}

export function FeatureCard({ feature, onClick, isInProgress, allFeatures = [], activeAgent }: FeatureCardProps) {
  const categoryColor = getCategoryColor(feature.category)
  const isBlocked = feature.blocked || (feature.blocking_dependencies && feature.blocking_dependencies.length > 0)
  const hasActiveAgent = !!activeAgent

  return (
    <button
      onClick={onClick}
      className={`
        w-full text-left neo-card p-4 cursor-pointer relative
        ${isInProgress ? 'animate-pulse-neo' : ''}
        ${feature.passes ? 'border-neo-done' : ''}
        ${isBlocked && !feature.passes ? 'border-neo-danger opacity-80' : ''}
        ${hasActiveAgent ? 'ring-2 ring-neo-progress ring-offset-2' : ''}
      `}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <span
            className="neo-badge"
            style={{ backgroundColor: categoryColor, color: 'var(--color-neo-text-on-bright)' }}
          >
            {feature.category}
          </span>
          <DependencyBadge feature={feature} allFeatures={allFeatures} compact />
        </div>
        <span className="font-mono text-sm text-neo-text-secondary">
          #{feature.priority}
        </span>
      </div>

      {/* Name */}
      <h3 className="font-display font-bold mb-1 line-clamp-2">
        {feature.name}
      </h3>

      {/* Description */}
      <p className="text-sm text-neo-text-secondary line-clamp-2 mb-3">
        {feature.description}
      </p>

      {/* Agent working on this feature */}
      {activeAgent && (
        <div className="flex items-center gap-2 mb-3 py-2 px-2 rounded bg-[var(--color-neo-progress)]/10 border border-[var(--color-neo-progress)]/30">
          <AgentAvatar name={activeAgent.agentName} state={activeAgent.state} size="sm" />
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold text-neo-progress">
              {activeAgent.agentName} is working on this!
            </div>
            {activeAgent.thought && (
              <div className="flex items-center gap-1 mt-0.5">
                <MessageCircle size={10} className="text-neo-text-secondary shrink-0" />
                <p className="text-[10px] text-neo-text-secondary truncate italic">
                  {activeAgent.thought}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Status */}
      <div className="flex items-center gap-2 text-sm">
        {isInProgress ? (
          <>
            <Loader2 size={16} className="animate-spin text-neo-progress" />
            <span className="text-neo-progress font-bold">Processing...</span>
          </>
        ) : feature.passes ? (
          <>
            <CheckCircle2 size={16} className="text-neo-done" />
            <span className="text-neo-done font-bold">Complete</span>
          </>
        ) : isBlocked ? (
          <>
            <Circle size={16} className="text-neo-danger" />
            <span className="text-neo-danger">Blocked</span>
          </>
        ) : (
          <>
            <Circle size={16} className="text-neo-text-secondary" />
            <span className="text-neo-text-secondary">Pending</span>
          </>
        )}
      </div>
    </button>
  )
}
