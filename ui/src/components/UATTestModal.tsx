import { useState } from 'react'
import {
  X,
  CheckCircle2,
  Circle,
  SkipForward,
  Trash2,
  Loader2,
  AlertCircle,
  Link2,
  Clock,
  PlayCircle,
  FileText,
  Image,
  Video,
  Bug,
  Layers,
  Map,
  Target
} from 'lucide-react'
import type { UATTestFeature } from '../lib/types'

interface UATTestModalProps {
  feature: UATTestFeature
  onClose: () => void
}

// Status icon mapping
function getStatusIcon(status: string) {
  switch (status) {
    case 'passed':
      return <CheckCircle2 size={24} className="text-[var(--color-neo-done)]" />
    case 'failed':
      return <Circle size={24} className="text-[var(--color-neo-danger)]" />
    case 'in_progress':
      return <Loader2 size={24} className="text-[var(--color-neo-progress)] animate-spin" />
    case 'needs-human':
      return <AlertCircle size={24} className="text-yellow-500" />
    case 'parked':
      return <SkipForward size={24} className="text-gray-500" />
    default: // pending
      return <Circle size={24} className="text-[var(--color-neo-text-secondary)]" />
  }
}

// Status badge color
function getStatusColor(status: string): string {
  switch (status) {
    case 'passed':
      return 'bg-[var(--color-neo-done)] text-white'
    case 'failed':
      return 'bg-[var(--color-neo-danger)] text-white'
    case 'in_progress':
      return 'bg-[var(--color-neo-progress)] text-white'
    case 'needs-human':
      return 'bg-yellow-500 text-white'
    case 'parked':
      return 'bg-gray-500 text-white'
    default:
      return 'bg-gray-400 text-white'
  }
}

// Phase badge color
function getPhaseColor(phase: string): string {
  const colors: Record<string, string> = {
    smoke: 'bg-orange-500 text-white',
    functional: 'bg-blue-500 text-white',
    regression: 'bg-purple-500 text-white',
    uat: 'bg-green-500 text-white'
  }
  return colors[phase] || 'bg-gray-500 text-white'
}

export function UATTestModal({ feature, onClose }: UATTestModalProps) {
  const [showEvidence, setShowEvidence] = useState(false)

  // Format duration
  const formatDuration = (seconds?: number): string => {
    if (!seconds) return 'N/A'
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    const mins = Math.floor(seconds / 60)
    const secs = (seconds % 60).toFixed(1)
    return `${mins}m ${secs}s`
  }

  // Format timestamp
  const formatTimestamp = (timestamp?: string): string => {
    if (!timestamp) return 'N/A'
    return new Date(timestamp).toLocaleString()
  }

  return (
    <div className="neo-modal-backdrop" onClick={onClose}>
      <div
        className="neo-modal w-full max-w-4xl max-h-[90vh] overflow-y-auto p-0"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-gray-900 border-b-3 border-[var(--color-neo-border)] z-10">
          <div className="flex items-start justify-between p-6">
            <div className="flex-1">
              {/* Badges */}
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <span className={`neo-badge ${getPhaseColor(feature.phase)}`}>
                  {feature.phase.toUpperCase()}
                </span>
                <span className="neo-badge bg-purple-500 text-white">
                  {feature.journey}
                </span>
                <span className={`neo-badge ${getStatusColor(feature.status)}`}>
                  {feature.status.replace('_', ' ').toUpperCase()}
                </span>
                <span className="neo-badge bg-gray-500 text-white">
                  {feature.test_type.toUpperCase()}
                </span>
              </div>

              {/* Title */}
              <h2 className="font-display text-2xl font-bold mb-2">
                {feature.scenario}
              </h2>

              {/* Metadata */}
              <div className="flex items-center gap-4 text-sm text-neo-text-secondary">
                <div className="flex items-center gap-1">
                  <Target size={14} />
                  <span className="font-mono">#{feature.priority}</span>
                </div>
                {feature.test_file && (
                  <div className="flex items-center gap-1 font-mono text-xs">
                    <FileText size={14} />
                    <span className="truncate max-w-xs">{feature.test_file}</span>
                  </div>
                )}
              </div>
            </div>

            <button
              onClick={onClose}
              className="neo-btn neo-btn-ghost p-2 shrink-0"
            >
              <X size={24} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Description */}
          <div>
            <h3 className="font-display font-bold mb-2 uppercase text-sm flex items-center gap-2">
              <FileText size={16} />
              What We're Testing
            </h3>
            <p className="text-[var(--color-neo-text-secondary)] whitespace-pre-wrap">
              {feature.description}
            </p>
          </div>

          {/* Expected Result */}
          <div>
            <h3 className="font-display font-bold mb-2 uppercase text-sm flex items-center gap-2">
              <Target size={16} />
              Expected Result
            </h3>
            <p className="text-[var(--color-neo-text-secondary)] whitespace-pre-wrap">
              {feature.expected_result}
            </p>
          </div>

          {/* Test Steps */}
          {feature.steps && feature.steps.length > 0 && (
            <div>
              <h3 className="font-display font-bold mb-2 uppercase text-sm flex items-center gap-2">
                <Layers size={16} />
                Test Steps ({feature.steps.length})
              </h3>
              <ol className="space-y-2">
                {feature.steps.map((step, index) => (
                  <li
                    key={index}
                    className="p-3 bg-[var(--color-neo-bg)] border-3 border-[var(--color-neo-border)]"
                  >
                    <div className="flex items-start gap-3">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-purple-500 text-white flex items-center justify-center text-sm font-bold">
                        {index + 1}
                      </span>
                      <p className="flex-1">{step}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Timing Information */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-[var(--color-neo-bg)] border-3 border-[var(--color-neo-border)]">
              <div className="flex items-center gap-2 text-sm text-neo-text-secondary mb-1">
                <Clock size={14} />
                Created
              </div>
              <div className="font-mono text-sm">
                {formatTimestamp(feature.created_at)}
              </div>
            </div>

            {feature.started_at && (
              <div className="p-4 bg-[var(--color-neo-bg)] border-3 border-[var(--color-neo-border)]">
                <div className="flex items-center gap-2 text-sm text-neo-text-secondary mb-1">
                  <PlayCircle size={14} />
                  Started
                </div>
                <div className="font-mono text-sm">
                  {formatTimestamp(feature.started_at)}
                </div>
              </div>
            )}

            {feature.completed_at && (
              <div className="p-4 bg-[var(--color-neo-bg)] border-3 border-[var(--color-neo-border)]">
                <div className="flex items-center gap-2 text-sm text-neo-text-secondary mb-1">
                  <CheckCircle2 size={14} />
                  Completed
                </div>
                <div className="font-mono text-sm">
                  {formatTimestamp(feature.completed_at)}
                </div>
              </div>
            )}
          </div>

          {/* Test Results (if executed) */}
          {feature.result && (
            <div className="p-4 bg-[var(--color-neo-bg)] border-3 border-[var(--color-neo-border)]">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display font-bold uppercase text-sm flex items-center gap-2">
                  <PlayCircle size={16} />
                  Test Results
                </h3>
                {feature.result.duration && (
                  <span className="font-mono text-sm">
                    Duration: {formatDuration(feature.result.duration)}
                  </span>
                )}
              </div>

              {/* Error Message */}
              {feature.result.error && (
                <div className="mb-4 p-4 bg-[var(--color-neo-error-bg)] border-3 border-[var(--color-neo-error-border)]">
                  <div className="flex items-center gap-2 mb-2 text-[var(--color-neo-error-text)] font-bold">
                    <Bug size={16} />
                    Error
                  </div>
                  <pre className="text-sm text-[var(--color-neo-error-text)] whitespace-pre-wrap font-mono">
                    {feature.result.error}
                  </pre>
                </div>
              )}

              {/* Console Logs */}
              {feature.result.logs && feature.result.logs.length > 0 && (
                <div className="mb-4">
                  <button
                    onClick={() => setShowEvidence(!showEvidence)}
                    className="neo-btn neo-btn-ghost text-sm w-full flex items-center justify-between"
                  >
                    <span className="flex items-center gap-2">
                      <FileText size={14} />
                      Console Logs ({feature.result.logs!.length})
                    </span>
                    <span>{showEvidence ? '▼' : '▶'}</span>
                  </button>
                  {showEvidence && (
                    <div className="mt-2 p-3 bg-black text-green-400 font-mono text-xs rounded border-2 border-gray-700 max-h-60 overflow-y-auto">
                      {feature.result.logs.map((log, index) => (
                        <div key={index} className="whitespace-pre-wrap">
                          {log}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Evidence Links */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Screenshot */}
                {feature.result.screenshot && (
                  <div>
                    <div className="flex items-center gap-2 text-sm font-bold mb-2">
                      <Image size={14} />
                      Screenshot
                    </div>
                    <a
                      href={feature.result.screenshot}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="neo-btn neo-btn-ghost text-sm w-full flex items-center justify-center gap-2"
                    >
                      <Image size={14} />
                      View Screenshot
                    </a>
                  </div>
                )}

                {/* Video */}
                {feature.result.video && (
                  <div>
                    <div className="flex items-center gap-2 text-sm font-bold mb-2">
                      <Video size={14} />
                      Video Recording
                    </div>
                    <a
                      href={feature.result.video}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="neo-btn neo-btn-ghost text-sm w-full flex items-center justify-center gap-2"
                    >
                      <Video size={14} />
                      Watch Video
                    </a>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Dependencies */}
          {feature.dependencies && feature.dependencies.length > 0 && (
            <div>
              <h3 className="font-display font-bold mb-2 uppercase text-sm flex items-center gap-2">
                <Link2 size={16} />
                Depends On ({feature.dependencies.length})
              </h3>
              <div className="flex flex-wrap gap-2">
                {feature.dependencies.map(depId => (
                  <span
                    key={depId}
                    className="neo-badge bg-purple-500 text-white"
                  >
                    Test #{depId}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* DevLayer Card Link */}
          {feature.devlayer_card_id && (
            <div className="p-4 bg-[var(--color-neo-warning-bg)] border-3 border-[var(--color-neo-warning-border)]">
              <div className="flex items-center gap-2 text-[var(--color-neo-warning-text)] font-bold mb-2">
                <Bug size={16} />
                Bug Report Created
              </div>
              <p className="text-sm text-[var(--color-neo-warning-text)] mb-2">
                This test failure created a DevLayer card:
              </p>
              <a
                href={`#card-${feature.devlayer_card_id}`}
                className="neo-btn neo-btn-warning text-sm"
              >
                View Card {feature.devlayer_card_id}
              </a>
            </div>
          )}

          {/* Status History */}
          {feature.status_history && feature.status_history.length > 0 && (
            <div>
              <h3 className="font-display font-bold mb-2 uppercase text-sm flex items-center gap-2">
                <Clock size={16} />
                Status History ({feature.status_history.length})
              </h3>
              <div className="space-y-2">
                {feature.status_history.map((entry, index) => (
                  <div
                    key={index}
                    className="p-3 bg-[var(--color-neo-bg)] border-2 border-[var(--color-neo-border)] text-sm"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`neo-badge ${getStatusColor(entry.from)} text-xs`}>
                        {entry.from}
                      </span>
                      <span>→</span>
                      <span className={`neo-badge ${getStatusColor(entry.to)} text-xs`}>
                        {entry.to}
                      </span>
                      <span className="ml-auto font-mono text-xs text-neo-text-secondary">
                        {formatTimestamp(entry.at)}
                      </span>
                    </div>
                    {entry.agent && (
                      <div className="text-xs text-neo-text-secondary">
                        Agent: {entry.agent}
                      </div>
                    )}
                    {entry.reason && (
                      <div className="text-xs text-neo-text-secondary mt-1">
                        {entry.reason}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-6 border-t-3 border-[var(--color-neo-border)] bg-[var(--color-neo-bg)]">
          <button
            onClick={onClose}
            className="neo-btn neo-btn-primary w-full"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
