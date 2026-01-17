import { useEffect, useCallback } from 'react'
import { X, Keyboard } from 'lucide-react'

interface Shortcut {
  key: string
  description: string
  context?: string
}

const shortcuts: Shortcut[] = [
  { key: '?', description: 'Show keyboard shortcuts' },
  { key: 'D', description: 'Toggle debug panel' },
  { key: 'T', description: 'Toggle terminal tab' },
  { key: 'N', description: 'Add new feature', context: 'with project' },
  { key: 'E', description: 'Expand project with AI', context: 'with features' },
  { key: 'A', description: 'Toggle AI assistant', context: 'with project' },
  { key: 'G', description: 'Toggle Kanban/Graph view', context: 'with project' },
  { key: ',', description: 'Open settings' },
  { key: 'Esc', description: 'Close modal/panel' },
]

interface KeyboardShortcutsHelpProps {
  onClose: () => void
}

export function KeyboardShortcutsHelp({ onClose }: KeyboardShortcutsHelpProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === '?') {
        e.preventDefault()
        onClose()
      }
    },
    [onClose]
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="neo-card p-6 max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Keyboard size={20} className="text-neo-accent" />
            <h2 className="font-display text-lg font-bold">Keyboard Shortcuts</h2>
          </div>
          <button
            onClick={onClose}
            className="neo-btn p-1.5"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Shortcuts list */}
        <ul className="space-y-2">
          {shortcuts.map((shortcut) => (
            <li
              key={shortcut.key}
              className="flex items-center justify-between py-2 border-b border-neo-border/30 last:border-0"
            >
              <div className="flex items-center gap-2">
                <kbd className="px-2 py-1 text-sm font-mono bg-neo-bg rounded border border-neo-border shadow-neo-sm min-w-[2rem] text-center">
                  {shortcut.key}
                </kbd>
                <span className="text-neo-text">{shortcut.description}</span>
              </div>
              {shortcut.context && (
                <span className="text-xs text-neo-muted">{shortcut.context}</span>
              )}
            </li>
          ))}
        </ul>

        {/* Footer */}
        <p className="text-xs text-neo-muted text-center mt-6">
          Press ? or Esc to close
        </p>
      </div>
    </div>
  )
}
