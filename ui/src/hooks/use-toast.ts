/**
 * Toast Hook
 *
 * Simple toast notification system.
 * Returns a toast function that logs to console and could be extended
 * to show UI notifications.
 */

import { useCallback } from 'react'

export interface Toast {
  id: string
  title?: string
  description?: string
  variant?: 'default' | 'destructive'
}

export interface ToastReturn {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
  toast: (props: Omit<Toast, 'id'>) => void
}

// Simple in-memory storage for toasts (can be replaced with proper state management)
let toasts: Toast[] = []

export function useToast(): ToastReturn {
  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const newToast: Toast = {
      id: Math.random().toString(36).substring(2, 9),
      ...toast
    }
    toasts.push(newToast)

    // Auto-remove after 5 seconds
    setTimeout(() => {
      removeToast(newToast.id)
    }, 5000)
  }, [])

  const removeToast = useCallback((id: string) => {
    toasts = toasts.filter(t => t.id !== id)
  }, [])

  const toast = useCallback((props: Omit<Toast, 'id'>) => {
    // Log to console
    const variant = props.variant === 'destructive' ? '❌' : '✅'
    console.log(`${variant} ${props.title}${props.description ? ': ' + props.description : ''}`)

    // Also add to toasts array
    addToast(props)
  }, [addToast])

  return {
    toasts: [...toasts], // Return a copy
    addToast,
    removeToast,
    toast
  }
}
