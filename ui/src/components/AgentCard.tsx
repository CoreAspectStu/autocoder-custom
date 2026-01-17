import { MessageCircle } from 'lucide-react'
import { AgentAvatar } from './AgentAvatar'
import type { ActiveAgent } from '../lib/types'

interface AgentCardProps {
  agent: ActiveAgent
}

// Get a friendly state description
function getStateText(state: ActiveAgent['state']): string {
  switch (state) {
    case 'idle':
      return 'Waiting...'
    case 'thinking':
      return 'Thinking...'
    case 'working':
      return 'Coding...'
    case 'testing':
      return 'Testing...'
    case 'success':
      return 'Done!'
    case 'error':
      return 'Hit an issue'
    case 'struggling':
      return 'Retrying...'
    default:
      return 'Working...'
  }
}

// Get state color
function getStateColor(state: ActiveAgent['state']): string {
  switch (state) {
    case 'success':
      return 'text-neo-done'
    case 'error':
    case 'struggling':
      return 'text-neo-danger'
    case 'working':
    case 'testing':
      return 'text-neo-progress'
    case 'thinking':
      return 'text-neo-pending'
    default:
      return 'text-neo-text-secondary'
  }
}

export function AgentCard({ agent }: AgentCardProps) {
  const isActive = ['thinking', 'working', 'testing'].includes(agent.state)

  return (
    <div
      className={`
        neo-card p-3 min-w-[180px] max-w-[220px]
        ${isActive ? 'animate-pulse-neo' : ''}
        transition-all duration-300
      `}
    >
      {/* Header with avatar and name */}
      <div className="flex items-center gap-2 mb-2">
        <AgentAvatar name={agent.agentName} state={agent.state} size="sm" />
        <div className="flex-1 min-w-0">
          <div className="font-display font-bold text-sm truncate">
            {agent.agentName}
          </div>
          <div className={`text-xs ${getStateColor(agent.state)}`}>
            {getStateText(agent.state)}
          </div>
        </div>
      </div>

      {/* Feature info */}
      <div className="mb-2">
        <div className="text-xs text-neo-text-secondary mb-0.5">
          Feature #{agent.featureId}
        </div>
        <div className="text-sm font-medium truncate" title={agent.featureName}>
          {agent.featureName}
        </div>
      </div>

      {/* Thought bubble */}
      {agent.thought && (
        <div className="relative mt-2 pt-2 border-t-2 border-neo-border/30">
          <div className="flex items-start gap-1.5">
            <MessageCircle size={14} className="text-neo-progress shrink-0 mt-0.5" />
            <p
              className="text-xs text-neo-text-secondary line-clamp-2 italic"
              title={agent.thought}
            >
              {agent.thought}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
