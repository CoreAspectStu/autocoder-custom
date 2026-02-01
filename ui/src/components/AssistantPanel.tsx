/**
 * Assistant Panel Component
 *
 * Slide-in panel container for the project assistant chat.
 * Slides in from the right side of the screen.
 * Manages conversation state with localStorage persistence.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { X, Bot, FlaskConical } from 'lucide-react'
import { AssistantChat } from './AssistantChat'
import { useConversation } from '../hooks/useConversations'
import type { ChatMessage } from '../lib/types'

interface AssistantPanelProps {
  projectName: string
  isOpen: boolean
  onClose: () => void
  mode?: 'dev' | 'uat'  // Add mode prop
}

const STORAGE_KEY_PREFIX = 'assistant-conversation-'

function getStoredConversationId(projectName: string, mode: 'dev' | 'uat'): number | null {
  try {
    const key = `${STORAGE_KEY_PREFIX}${projectName}-${mode}`
    const stored = localStorage.getItem(key)
    if (stored) {
      const data = JSON.parse(stored)
      return data.conversationId || null
    }
  } catch {
    // Invalid stored data, ignore
  }
  return null
}

function setStoredConversationId(projectName: string, mode: 'dev' | 'uat', conversationId: number | null) {
  const key = `${STORAGE_KEY_PREFIX}${projectName}-${mode}`
  if (conversationId) {
    localStorage.setItem(key, JSON.stringify({ conversationId }))
  } else {
    localStorage.removeItem(key)
  }
}

export function AssistantPanel({ projectName, isOpen, onClose, mode = 'dev' }: AssistantPanelProps) {
  // Ref for the close button (used to blur focus on close)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  // Load initial conversation ID from localStorage (mode-aware)
  const [conversationId, setConversationId] = useState<number | null>(() =>
    getStoredConversationId(projectName, mode)
  )

  // Fetch conversation details when we have an ID
  const { data: conversationDetail, isLoading: isLoadingConversation } = useConversation(
    projectName,
    conversationId
  )

  // Convert API messages to ChatMessage format for the chat component
  const initialMessages: ChatMessage[] | undefined = conversationDetail?.messages?.map((msg) => ({
    id: `db-${msg.id}`,
    role: msg.role,
    content: msg.content,
    timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
  }))

  // Persist conversation ID changes to localStorage (mode-aware)
  useEffect(() => {
    setStoredConversationId(projectName, mode, conversationId)
  }, [projectName, mode, conversationId])

  // Reset conversation ID when project or mode changes
  useEffect(() => {
    setConversationId(getStoredConversationId(projectName, mode))
  }, [projectName, mode])

  // Handle starting a new chat
  const handleNewChat = useCallback(() => {
    setConversationId(null)
  }, [])

  // Handle selecting a conversation from history
  const handleSelectConversation = useCallback((id: number) => {
    setConversationId(id)
  }, [])

  // Handle when a new conversation is created (from WebSocket)
  const handleConversationCreated = useCallback((id: number) => {
    setConversationId(id)
  }, [])

  // Handle panel close with focus cleanup to avoid aria-hidden accessibility warning
  const handleClose = useCallback(() => {
    // Blur the close button before closing to prevent aria-hidden accessibility issue
    // When aria-hidden is set to true on the panel, no element inside should have focus
    closeButtonRef.current?.blur()
    // Call the original onClose callback
    onClose()
  }, [onClose])

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
              {mode === 'uat' ? <FlaskConical size={18} className="text-purple-600" /> : <Bot size={18} />}
            </div>
            <div>
              <h2 className="font-display font-bold text-neo-text-on-bright">
                {mode === 'uat' ? 'UAT Test Planner' : 'Project Assistant'}
              </h2>
              <p className="text-xs text-neo-text-on-bright opacity-80 font-mono">
                {projectName} {mode === 'uat' && <span className="text-purple-600">(UAT Mode)</span>}
              </p>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            onClick={handleClose}
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
          {isOpen && (
            <AssistantChat
              projectName={projectName}
              mode={mode}
              conversationId={conversationId}
              initialMessages={initialMessages}
              isLoadingConversation={isLoadingConversation}
              onNewChat={handleNewChat}
              onSelectConversation={handleSelectConversation}
              onConversationCreated={handleConversationCreated}
            />
          )}
        </div>
      </div>
    </>
  )
}
