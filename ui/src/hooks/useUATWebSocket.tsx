/**
 * UAT WebSocket Hook
 *
 * Manages real-time WebSocket connection for UAT test execution updates.
 * Provides live progress tracking, test status updates, and agent monitoring.
 *
 * Features:
 * - Auto-reconnect with exponential backoff
 * - Connection status indicator
 * - Event-based message handling
 * - Graceful disconnection
 * - Message queue for offline updates
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { useToast } from '@/hooks/use-toast'

// ============================================================================
// Types
// ============================================================================

export type UATWebSocketMessageType =
  | 'connected'
  | 'test_started'
  | 'test_passed'
  | 'test_failed'
  | 'agent_started'
  | 'agent_stopped'
  | 'progress_stats'
  | 'cycle_complete'
  | 'error'
  | 'pong'

export interface UATWebSocketMessage<T = any> {
  type: UATWebSocketMessageType
  data: T
}

export interface UATTestStartedData {
  test_id: string
  scenario: string
  agent_id: string
  timestamp: string
}

export interface UATTestPassedData {
  test_id: string
  scenario: string
  duration: number
  timestamp: string
}

export interface UATTestFailedData {
  test_id: string
  scenario: string
  error: string
  duration: number
  timestamp: string
}

export interface UATAgentStartedData {
  agent_id: string
  agent_name: string
  timestamp: string
}

export interface UATAgentStoppedData {
  agent_id: string
  timestamp: string
}

export interface UATProgressStatsData {
  total_tests: number
  passed: number
  failed: number
  running: number
  pending: number
  active_agents: number
  timestamp?: string
}

export interface UATCycleCompleteData {
  summary: {
    total_journeys?: number
    total_scenarios?: number
    passed_scenarios?: number
    failed_scenarios?: number
    pass_rate?: number
  }
  total_duration: number
  timestamp: string
}

export interface UATConnectedData {
  cycle_id: string
  timestamp: string
}

export interface UATErrorData {
  message: string
  timestamp: string
}

export type UATConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface UseUATWebSocketOptions {
  cycleId: string
  autoConnect?: boolean
  reconnectInterval?: number
  maxReconnectAttempts?: number
  onTestStarted?: (data: UATTestStartedData) => void
  onTestPassed?: (data: UATTestPassedData) => void
  onTestFailed?: (data: UATTestFailedData) => void
  onAgentStarted?: (data: UATAgentStartedData) => void
  onAgentStopped?: (data: UATAgentStoppedData) => void
  onProgressStats?: (data: UATProgressStatsData) => void
  onCycleComplete?: (data: UATCycleCompleteData) => void
  onError?: (data: UATErrorData) => void
}

export interface UseUATWebSocketReturn {
  status: UATConnectionStatus
  connected: boolean
  sendMessage: (type: string, data?: any) => void
  reconnect: () => void
  disconnect: () => void
  latestStats: UATProgressStatsData | null
  messageHistory: UATWebSocketMessage[]
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useUATWebSocket(options: UseUATWebSocketOptions): UseUATWebSocketReturn {
  const {
    cycleId,
    autoConnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
    onTestStarted,
    onTestPassed,
    onTestFailed,
    onAgentStarted,
    onAgentStopped,
    onProgressStats,
    onCycleComplete,
    onError
  } = options

  const [status, setStatus] = useState<UATConnectionStatus>('disconnected')
  const [latestStats, setLatestStats] = useState<UATProgressStatsData | null>(null)
  const [messageHistory, setMessageHistory] = useState<UATWebSocketMessage[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const manuallyClosedRef = useRef(false)

  const { toast } = useToast()

  // Build WebSocket URL
  const getWebSocketUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    return `${protocol}//${host}/api/uat/ws/${cycleId}`
  }, [cycleId])

  // Handle incoming messages
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const message: UATWebSocketMessage = JSON.parse(event.data)

      // Add to history
      setMessageHistory(prev => [...prev.slice(-99), message])

      switch (message.type) {
        case 'connected':
          setStatus('connected')
          reconnectAttemptsRef.current = 0
          break

        case 'test_started':
          onTestStarted?.(message.data as UATTestStartedData)
          break

        case 'test_passed':
          onTestPassed?.(message.data as UATTestPassedData)
          break

        case 'test_failed':
          onTestFailed?.(message.data as UATTestFailedData)
          break

        case 'agent_started':
          onAgentStarted?.(message.data as UATAgentStartedData)
          break

        case 'agent_stopped':
          onAgentStopped?.(message.data as UATAgentStoppedData)
          break

        case 'progress_stats':
          const stats = message.data as UATProgressStatsData
          setLatestStats(stats)
          onProgressStats?.(stats)
          break

        case 'cycle_complete':
          setStatus('disconnected')
          onCycleComplete?.(message.data as UATCycleCompleteData)
          break

        case 'error':
          const errorData = message.data as UATErrorData
          toast({
            variant: 'destructive',
            title: 'UAT Test Error',
            description: errorData.message
          })
          onError?.(errorData)
          break

        case 'pong':
          // Response to ping, no action needed
          break
      }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error)
    }
  }, [onTestStarted, onTestPassed, onTestFailed, onAgentStarted, onAgentStopped, onProgressStats, onCycleComplete, onError, toast])

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    setStatus('connecting')

    try {
      const ws = new WebSocket(getWebSocketUrl())

      ws.onopen = () => {
        setStatus('connected')
        reconnectAttemptsRef.current = 0
      }

      ws.onmessage = handleMessage

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setStatus('error')
      }

      ws.onclose = (event) => {
        setStatus('disconnected')
        wsRef.current = null

        // Auto-reconnect if not manually closed
        if (!manuallyClosedRef.current && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++
          const delay = reconnectInterval * Math.pow(1.5, reconnectAttemptsRef.current - 1)

          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, delay)
        } else if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
          toast({
            variant: 'destructive',
            title: 'Connection Failed',
            description: 'Could not reconnect to UAT WebSocket. Please refresh the page.'
          })
        }
      }

      wsRef.current = ws
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      setStatus('error')
    }
  }, [getWebSocketUrl, handleMessage, reconnectInterval, maxReconnectAttempts, toast])

  // Send message to server
  const sendMessage = useCallback((type: string, data?: any) => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, data }))
    }
  }, [])

  // Request fresh stats from server
  const requestStats = useCallback(() => {
    sendMessage('request_stats')
  }, [sendMessage])

  // Manual reconnect
  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0
    manuallyClosedRef.current = false
    connect()
  }, [connect])

  // Disconnect (manual)
  const disconnect = useCallback(() => {
    manuallyClosedRef.current = true

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    setStatus('disconnected')
  }, [])

  // Send periodic ping to keep connection alive
  useEffect(() => {
    if (status !== 'connected') return

    const pingInterval = setInterval(() => {
      sendMessage('ping')
    }, 30000) // Ping every 30 seconds

    return () => clearInterval(pingInterval)
  }, [status, sendMessage])

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect && cycleId) {
      connect()
    }

    return () => {
      disconnect()
    }
  }, [cycleId, autoConnect]) // Note: don't include connect/disconnect to avoid reconnect loops

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  return {
    status,
    connected: status === 'connected',
    sendMessage,
    reconnect,
    disconnect,
    latestStats,
    messageHistory
  }
}

// ============================================================================
// Helper Components
// ============================================================================

export interface UATConnectionIndicatorProps {
  status: UATConnectionStatus
  className?: string
}

export function UATConnectionIndicator({ status, className = '' }: UATConnectionIndicatorProps) {
  const getStatusColor = () => {
    switch (status) {
      case 'connected':
        return 'bg-green-500'
      case 'connecting':
        return 'bg-yellow-500 animate-pulse'
      case 'disconnected':
        return 'bg-gray-400'
      case 'error':
        return 'bg-red-500'
    }
  }

  const getStatusLabel = () => {
    switch (status) {
      case 'connected':
        return 'Connected'
      case 'connecting':
        return 'Connecting...'
      case 'disconnected':
        return 'Disconnected'
      case 'error':
        return 'Connection Error'
    }
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className={`w-2 h-2 rounded-full ${getStatusColor()}`} />
      <span className="text-xs text-gray-600 dark:text-gray-400">
        {getStatusLabel()}
      </span>
    </div>
  )
}
