/**
 * UAT Mode Context
 *
 * Provides UAT mode state across the application.
 * When UAT mode is active, all data queries route to uat_tests.db instead of features.db.
 */

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'

const UAT_MODE_KEY = 'autocoder-uat-mode'

type UATMode = 'dev' | 'uat'

interface UATModeContextType {
  mode: UATMode
  setMode: (mode: UATMode) => void
  toggleMode: () => void
  isUATMode: boolean
}

const UATModeContext = createContext<UATModeContextType | undefined>(undefined)

interface UATModeProviderProps {
  children: ReactNode
}

export function UATModeProvider({ children }: UATModeProviderProps) {
  const [mode, setModeState] = useState<UATMode>(() => {
    try {
      const stored = localStorage.getItem(UAT_MODE_KEY)
      return (stored === 'uat' ? 'uat' : 'dev') as UATMode
    } catch {
      return 'dev'
    }
  })

  // Persist mode to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(UAT_MODE_KEY, mode)
    } catch (error) {
      console.error('Failed to persist UAT mode:', error)
    }
  }, [mode])

  const setMode = (newMode: UATMode) => {
    setModeState(newMode)
  }

  const toggleMode = () => {
    const startTime = performance.now()
    setModeState(prev => {
      const newMode = prev === 'dev' ? 'uat' : 'dev'
      // Measure time until state update is processed
      requestAnimationFrame(() => {
        const endTime = performance.now()
        const duration = endTime - startTime
        console.log(`[UAT Mode] Switched from ${prev} to ${newMode} in ${duration.toFixed(2)}ms`)
        if (duration > 500) {
          console.warn(`[UAT Mode] Performance warning: Mode switch took ${duration.toFixed(2)}ms (exceeds 500ms requirement)`)
        }
      })
      return newMode
    })
  }

  const isUATMode = mode === 'uat'

  return (
    <UATModeContext.Provider value={{ mode, setMode, toggleMode, isUATMode }}>
      {children}
    </UATModeContext.Provider>
  )
}

/**
 * Hook to access UAT mode context
 */
export function useUATMode(): UATModeContextType {
  const context = useContext(UATModeContext)
  if (context === undefined) {
    throw new Error('useUATMode must be used within a UATModeProvider')
  }
  return context
}
