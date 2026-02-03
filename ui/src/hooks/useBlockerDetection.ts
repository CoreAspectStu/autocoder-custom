/**
 * React Hook for Blocker Detection and Resolution
 *
 * Provides methods for detecting blockers and managing their resolution
 */

import { useState, useCallback } from 'react'
import * as api from '../lib/api'

export interface Blocker {
  id: string
  blocker_type: 'api_key' | 'config_decision' | 'resource_missing' | 'service_unavailable'
  service: string
  key_name?: string
  description: string
  affected_tests: string[]
  suggested_actions: string[]
  priority: 'critical' | 'high' | 'medium' | 'low'
  context?: Record<string, any>
}

export interface BlockerDetectionResult {
  blockers_detected: boolean
  blockers: Blocker[]
  summary: string
  project_name: string
}

export interface BlockerResponse {
  blocker_id: string
  action: 'provide_key' | 'skip' | 'mock' | 'wait' | 'enable' | 'disable'
  value?: string
}

export interface BlockerResolution {
  blocker_id: string
  status: 'resolved' | 'skipped' | 'pending' | 'failed'
  message: string
}

export function useBlockerDetection(projectName: string | null) {
  const [blockers, setBlockers] = useState<Blocker[]>([])
  const [isDetecting, setIsDetecting] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [responses, setResponses] = useState<Record<string, BlockerResponse>>({})

  const detectBlockers = useCallback(async () => {
    if (!projectName) return

    setIsDetecting(true)
    try {
      // Get project path from registry
      const projectsResp = await fetch('/api/projects')
      const projects = await projectsResp.json()
      const project = projects.find((p: any) => p.name === projectName)

      if (!project) {
        throw new Error(`Project ${projectName} not found`)
      }

      const response = await fetch('/api/blocker/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_name: projectName,
          project_path: project.path
        })
      })

      if (!response.ok) {
        throw new Error('Failed to detect blockers')
      }

      const result: BlockerDetectionResult = await response.json()

      if (result.blockers_detected && result.blockers.length > 0) {
        setBlockers(result.blockers)
        setCurrentIndex(0)
      } else {
        setBlockers([])
      }

      return result
    } catch (error) {
      console.error('[BlockerDetection] Failed to detect blockers:', error)
      throw error
    } finally {
      setIsDetecting(false)
    }
  }, [projectName])

  const respondToBlocker = useCallback(async (response: BlockerResponse) => {
    try {
      const resp = await fetch('/api/blocker/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...response,
          project_name: projectName
        })
      })

      if (!resp.ok) {
        throw new Error('Failed to resolve blocker')
      }

      const result: BlockerResolution = await resp.json()

      // Store response
      setResponses(prev => ({
        ...prev,
        [response.blocker_id]: response
      }))

      // Move to next blocker
      if (currentIndex < blockers.length - 1) {
        setCurrentIndex(prev => prev + 1)
      }

      return result
    } catch (error) {
      console.error('[BlockerDetection] Failed to respond to blocker:', error)
      throw error
    }
  }, [projectName, blockers, currentIndex])

  const skipAll = useCallback(async () => {
    // Skip all remaining blockers
    for (let i = currentIndex; i < blockers.length; i++) {
      await respondToBlocker({
        blocker_id: blockers[i].id,
        action: 'skip'
      })
    }
  }, [blockers, currentIndex, respondToBlocker])

  const currentBlocker = blockers[currentIndex]

  return {
    blockers,
    isDetecting,
    currentIndex,
    currentBlocker,
    responses,
    detectBlockers,
    respondToBlocker,
    skipAll,
    setCurrentIndex,
    hasBlockers: blockers.length > 0,
    isComplete: currentIndex >= blockers.length && blockers.length > 0
  }
}
