/**
 * Start UAT Button Component
 *
 * Triggers test execution for approved UAT test plans.
 * Shows agent spawning progress and execution status.
 *
 * Feature #23: Start test agents from kanban board
 */

import { useState } from 'react'
import { Play, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { triggerUATExecution, getUATProgress } from '../lib/api'
import { useUATMode } from '../contexts/UATModeContext'

interface StartUATButtonProps {
  projectName: string | null
  pendingTestsCount: number
  onExecutionStarted?: () => void
}

export function StartUATButton({ projectName, pendingTestsCount, onExecutionStarted }: StartUATButtonProps) {
  const { isUATMode } = useUATMode()
  const [isStarting, setIsStarting] = useState(false)
  const [status, setStatus] = useState<'idle' | 'starting' | 'running' | 'error'>('idle')
  const [message, setMessage] = useState<string>('')
  const [agentCount, setAgentCount] = useState<number>(0)

  // Only show in UAT mode with pending tests
  if (!projectName || !isUATMode || pendingTestsCount === 0) {
    return null
  }

  const handleStartUAT = async () => {
    setIsStarting(true)
    setStatus('starting')
    setMessage('Initializing test execution...')
    setAgentCount(0)

    try {
      // For now, use a hardcoded cycle_id or get from state
      // In production, this would come from the approved test plan
      const cycleId = localStorage.getItem(`uat_cycle_${projectName}`) || 'latest'

      // Trigger test execution
      const result = await triggerUATExecution(cycleId, projectName)

      console.log('[StartUAT] Execution triggered:', result)

      setStatus('running')
      setAgentCount(result.agents_spawned || 0)
      setMessage(`${result.agents_spawned || 0} test agents spawned successfully`)

      // Notify parent component
      onExecutionStarted?.()

      // Start polling for progress
      pollProgress(cycleId)

    } catch (error) {
      console.error('[StartUAT] Failed to start execution:', error)
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Failed to start test execution')
    } finally {
      setIsStarting(false)
    }
  }

  const pollProgress = async (cycleId: string) => {
    try {
      const progress = await getUATProgress(cycleId)
      console.log('[StartUAT] Progress update:', progress)

      setAgentCount(progress.active_agents)

      // Continue polling if tests are still running
      if (progress.running > 0) {
        setTimeout(() => pollProgress(cycleId), 2000)
      } else {
        setStatus('idle')
        setMessage('Test execution complete')
      }
    } catch (error) {
      console.error('[StartUAT] Failed to get progress:', error)
    }
  }

  return (
    <div className="flex items-center gap-3">
      {/* Status indicator */}
      {status !== 'idle' && (
        <div className="flex items-center gap-2 text-sm">
          {status === 'starting' && (
            <>
              <Loader2 className="w-4 h-4 text-purple-500 animate-spin" />
              <span className="text-gray-600 dark:text-gray-400">{message}</span>
            </>
          )}

          {status === 'running' && (
            <>
              <CheckCircle className="w-4 h-4 text-green-500" />
              <span className="text-gray-600 dark:text-gray-400">
                {agentCount} agents running
              </span>
            </>
          )}

          {status === 'error' && (
            <>
              <AlertCircle className="w-4 h-4 text-red-500" />
              <span className="text-red-600 dark:text-red-400">{message}</span>
            </>
          )}
        </div>
      )}

      {/* Start UAT button */}
      <button
        onClick={handleStartUAT}
        disabled={isStarting || status === 'running'}
        className={`
          neo-btn text-sm py-2 px-4 transition-all duration-200
          flex items-center gap-2 font-semibold
          ${status === 'running'
            ? 'bg-green-500 text-white border-green-600 cursor-default'
            : 'bg-purple-500 hover:bg-purple-600 text-white border-purple-600'
          }
          ${isStarting ? 'opacity-75 cursor-wait' : ''}
        `}
        title={`Start ${pendingTestsCount} pending UAT tests`}
      >
        {isStarting ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Starting...
          </>
        ) : status === 'running' ? (
          <>
            <CheckCircle className="w-4 h-4" />
            Running ({agentCount})
          </>
        ) : (
          <>
            <Play className="w-4 h-4" />
            Start UAT
          </>
        )}
      </button>
    </div>
  )
}
