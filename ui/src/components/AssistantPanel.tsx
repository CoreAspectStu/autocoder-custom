/**
 * Assistant Panel Component
 *
 * Slide-in panel container for the project assistant chat.
 * Slides in from the right side of the screen.
 */

import { X, Bot } from 'lucide-react'
import { AssistantChat } from './AssistantChat'

interface AssistantPanelProps {
  projectName: string
  isOpen: boolean
  onClose: () => void
}

export function AssistantPanel({ projectName, isOpen, onClose }: AssistantPanelProps) {
  return (
    <>
      {/* Backdrop - click to close */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40 transition-opacity duration-300"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Panel */}
      <div
        className={`
          fixed right-0 top-0 bottom-0 z-50
          w-[400px] max-w-[90vw]
          bg-neo-card
          border-l-4 border-[var(--color-neo-border)]
          transform transition-transform duration-300 ease-out
          flex flex-col
          ${isOpen ? 'translate-x-0' : 'translate-x-full'}
        `}
        style={{ boxShadow: 'var(--shadow-neo-left-lg)' }}
        role="dialog"
        aria-label="Project Assistant"
        aria-hidden={!isOpen}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b-3 border-neo-border bg-neo-progress">
          <div className="flex items-center gap-2">
            <div
              className="bg-neo-card border-2 border-neo-border p-1.5"
              style={{ boxShadow: 'var(--shadow-neo-sm)' }}
            >
              <Bot size={18} />
            </div>
            <div>
              <h2 className="font-display font-bold text-neo-text-on-bright">Project Assistant</h2>
              <p className="text-xs text-neo-text-on-bright opacity-80 font-mono">{projectName}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="
              neo-btn neo-btn-ghost
              p-2
              bg-[var(--color-neo-card)] border-[var(--color-neo-border)]
              hover:bg-[var(--color-neo-bg)]
              text-[var(--color-neo-text)]
            "
            title="Close Assistant (Press A)"
            aria-label="Close Assistant"
          >
            <X size={18} />
          </button>
        </div>

        {/* Chat area */}
        <div className="flex-1 overflow-hidden">
          {isOpen && <AssistantChat projectName={projectName} />}
        </div>
      </div>
    </>
  )
}
