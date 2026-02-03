/**
 * Skeleton Loader Component
 *
 * Shows a loading animation during async operations like
 * connection testing, data fetching, etc.
 *
 * Usage:
 *   <SkeletonLoader message="Testing connection..." />
 *   <SkeletonLoader message="Loading..." size="large" />
 */

import { Loader2 } from 'lucide-react'

interface SkeletonLoaderProps {
  message?: string
  size?: 'small' | 'medium' | 'large'
  className?: string
}

export function SkeletonLoader({
  message = 'Loading...',
  size = 'medium',
  className = ''
}: SkeletonLoaderProps) {
  const sizeClasses = {
    small: 'w-6 h-6',
    medium: 'w-12 h-12',
    large: 'w-16 h-16'
  }

  const textSizeClasses = {
    small: 'text-sm',
    medium: 'text-base',
    large: 'text-lg'
  }

  return (
    <div className={`flex flex-col items-center gap-4 p-12 ${className}`}>
      <Loader2 className={`${sizeClasses[size]} text-purple-500 animate-spin`} />
      {message && (
        <p className={`${textSizeClasses[size]} text-gray-600 dark:text-gray-400`}>
          {message}
        </p>
      )}
    </div>
  )
}

/**
 * Inline Skeleton - for use within forms/cards
 */
interface InlineSkeletonProps {
  height?: string
  className?: string
}

export function InlineSkeleton({
  height = 'h-4',
  className = ''
}: InlineSkeletonProps) {
  return (
    <div
      className={`bg-gray-200 dark:bg-gray-700 rounded animate-pulse ${height} ${className}`}
      role="status"
      aria-label="Loading"
    >
      <span className="sr-only">Loading...</span>
    </div>
  )
}

/**
 * Card Skeleton - mimics a card layout during loading
 */
export function CardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`p-6 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 ${className}`}>
      <div className="flex items-start gap-4 mb-4">
        <div className="w-12 h-12 bg-gray-200 dark:bg-gray-700 rounded-lg animate-pulse" />
        <div className="flex-1 space-y-2">
          <InlineSkeleton height="h-5" className="w-3/4" />
          <InlineSkeleton height="h-4" className="w-1/2" />
        </div>
      </div>
      <div className="space-y-2">
        <InlineSkeleton height="h-4" />
        <InlineSkeleton height="h-4" className="w-5/6" />
        <InlineSkeleton height="h-4" className="w-4/6" />
      </div>
    </div>
  )
}

/**
 * Connection Test Skeleton - specifically for connection testing UI
 */
interface ConnectionTestSkeletonProps {
  service: string
  className?: string
}

export function ConnectionTestSkeleton({
  service,
  className = ''
}: ConnectionTestSkeletonProps) {
  return (
    <div className={`flex flex-col items-center gap-4 p-8 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-200 dark:border-purple-800 ${className}`}>
      <div className="flex items-center gap-3">
        <Loader2 className="w-8 h-8 text-purple-500 animate-spin" />
        <div>
          <p className="font-medium text-gray-900 dark:text-gray-100">
            Testing {service} connection...
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Please wait while we verify the service is available
          </p>
        </div>
      </div>
      <InlineSkeleton height="h-2" className="w-full max-w-xs" />
    </div>
  )
}

export default SkeletonLoader
