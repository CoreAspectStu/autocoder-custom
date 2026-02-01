import { FlaskConical, Clock, AlertCircle } from 'lucide-react'
import { AgentAvatar } from './AgentAvatar'
import type { ActiveTestAgent } from '../lib/types'

interface TestAgentCardProps {
  agent: ActiveTestAgent
}

// Get a friendly state description for test agents
function getTestStateText(state: ActiveTestAgent['state']): string {
  switch (state) {
    case 'idle':
      return 'Waiting for test...'
    case 'claiming':
      return 'Claiming test...'
    case 'running':
      return 'Running test...'
    case 'passed':
      return 'Test passed!'
    case 'failed':
      return 'Test failed'
    case 'needs-human':
      return 'Needs human review'
    case 'parked':
      return 'Test parked'
    default:
      return 'Busy...'
  }
}

// Get state color for test agents
function getTestStateColor(state: ActiveTestAgent['state']): string {
  switch (state) {
    case 'passed':
      return 'text-neo-done'
    case 'failed':
      return 'text-red-600'
    case 'needs-human':
      return 'text-orange-500'
    case 'running':
      return 'text-neo-progress'
    case 'claiming':
      return 'text-neo-pending'
    default:
      return 'text-neo-text-secondary'
  }
}

// Get state background color for test agents
function getTestStateBgColor(state: ActiveTestAgent['state']): string {
  switch (state) {
    case 'passed':
      return 'bg-green-50 dark:bg-green-900/20'
    case 'failed':
      return 'bg-red-50 dark:bg-red-900/20'
    case 'needs-human':
      return 'bg-orange-50 dark:bg-orange-900/20'
    case 'running':
      return 'bg-blue-50 dark:bg-blue-900/20'
    case 'claiming':
      return 'bg-yellow-50 dark:bg-yellow-900/20'
    default:
      return 'bg-gray-50 dark:bg-gray-800/50'
  }
}

export function TestAgentCard({ agent }: TestAgentCardProps) {
  const isActive = agent.state === 'running' || agent.state === 'claiming'
  const stateColor = getTestStateColor(agent.state)
  const stateBgColor = getTestStateBgColor(agent.state)
  const stateText = getTestStateText(agent.state)

  return (
    <div
      className={`
        neo-card p-3 min-w-[200px] max-w-[240px]
        ${isActive ? 'animate-pulse-neo' : ''}
        ${stateBgColor}
        transition-all duration-300
      `}
    >
      {/* Test type badge */}
      <div className="flex justify-end mb-1">
        <span
          className={`
            inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-bold
            uppercase tracking-wide rounded border
            bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-700
          `}
        >
          <FlaskConical size={10} />
          TEST
        </span>
      </div>

      {/* Header with avatar and test name */}
      <div className="flex items-center gap-2 mb-2">
        <AgentAvatar name={`Agent ${agent.agentId}` as any} state={agent.state === 'running' ? 'working' : 'idle'} size="sm" />
        <div className="flex-1 min-w-0">
          <div className="font-bold text-xs truncate text-neo-text-primary">
            {agent.testName}
          </div>
          <div className={`text-[10px] ${stateColor} font-medium`}>
            {stateText}
          </div>
        </div>
      </div>

      {/* Test details */}
      <div className="space-y-1 text-[10px] text-neo-text-secondary">
        {/* Phase and Journey */}
        <div className="flex items-center justify-between">
          <span className="font-medium">Phase:</span>
          <span className="capitalize">{agent.phase}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="font-medium">Journey:</span>
          <span className="capitalize truncate max-w-[100px]" title={agent.journey}>
            {agent.journey}
          </span>
        </div>

        {/* Test ID */}
        <div className="flex items-center justify-between">
          <span className="font-medium">Test ID:</span>
          <span className="font-mono">#{agent.testId}</span>
        </div>

        {/* Duration (if available) */}
        {agent.duration !== undefined && (
          <div className="flex items-center justify-between">
            <span className="font-medium flex items-center gap-1">
              <Clock size={10} />
              Duration:
            </span>
            <span>{agent.duration.toFixed(1)}s</span>
          </div>
        )}

        {/* Error (if failed) */}
        {agent.error && (
          <div className="mt-2 p-2 bg-red-100 dark:bg-red-900/30 rounded border border-red-300 dark:border-red-700">
            <div className="flex items-start gap-1">
              <AlertCircle size={10} className="text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <span className="text-[9px] text-red-700 dark:text-red-300 line-clamp-2">
                {agent.error}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
