import { useState, useEffect } from 'react'
import { KanbanBoard } from './KanbanBoard'
import { ChatTab } from './ChatTab'
import { IssuesTab } from './IssuesTab'
import { StatusTab } from './StatusTab'
import { DebugLogViewer, type TabType as TerminalTabType } from './DebugLogViewer'
import type { Feature } from '../lib/types'

const TAB_STORAGE_KEY = 'autocoder-active-tab'

type TabId = 'kanban' | 'chat' | 'issues' | 'status' | 'terminal'

interface Tab {
  id: TabId
  label: string
  icon: string
  shortcut: string
}

const TABS: Tab[] = [
  { id: 'kanban', label: 'Kanban', icon: '📋', shortcut: '1' },
  { id: 'chat', label: 'Chat', icon: '💬', shortcut: '2' },
  { id: 'issues', label: 'Issues', icon: '🐛', shortcut: '3' },
  { id: 'status', label: 'Status', icon: '📊', shortcut: '4' },
  { id: 'terminal', label: 'Terminal', icon: '📺', shortcut: '5' },
]

interface TabLayoutProps {
  selectedProject: string | null
  features: {
    pending: Feature[]
    in_progress: Feature[]
    done: Feature[]
  } | undefined
  onFeatureClick: (feature: Feature) => void
  onAddFeature: () => void
  onExpandProject: () => void
  hasSpec: boolean
  onCreateSpec: () => void
  debugOpen: boolean
  debugPanelHeight: number
  debugActiveTab: TerminalTabType
  onDebugHeightChange: (height: number) => void
  onDebugTabChange: (tab: TerminalTabType) => void
}

export function TabLayout({
  selectedProject,
  features,
  onFeatureClick,
  onAddFeature,
  onExpandProject,
  hasSpec,
  onCreateSpec,
  debugOpen,
  debugPanelHeight,
  debugActiveTab,
  onDebugHeightChange,
  onDebugTabChange,
}: TabLayoutProps) {
  // Load active tab from localStorage
  const [activeTab, setActiveTab] = useState<TabId>(() => {
    try {
      const stored = localStorage.getItem(TAB_STORAGE_KEY)
      return (stored as TabId) || 'kanban'
    } catch {
      return 'kanban'
    }
  })

  // Persist active tab to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(TAB_STORAGE_KEY, activeTab)
    } catch {
      // localStorage not available
    }
  }, [activeTab])

  // Keyboard shortcuts: 1-5 to switch tabs
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return
      }

      const key = e.key
      if (key >= '1' && key <= '5') {
        e.preventDefault()
        const tabIndex = parseInt(key) - 1
        setActiveTab(TABS[tabIndex].id)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className="flex flex-col h-full">
      {/* Tab Navigation */}
      <div className="flex border-b border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              px-4 py-3 text-sm font-medium border-b-2 transition-colors
              ${
                activeTab === tab.id
                  ? 'border-purple-500 text-purple-600 dark:text-purple-400 bg-white dark:bg-gray-800'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
              }
            `}
            title={`Switch to ${tab.label} (${tab.shortcut})`}
          >
            <span className="mr-2">{tab.icon}</span>
            {tab.label}
            <span className="ml-2 text-xs text-gray-400">{tab.shortcut}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'kanban' && (
          <KanbanBoard
            features={features}
            onFeatureClick={onFeatureClick}
            onAddFeature={onAddFeature}
            onExpandProject={onExpandProject}
            hasSpec={hasSpec}
            onCreateSpec={onCreateSpec}
          />
        )}

        {activeTab === 'chat' && (
          <ChatTab selectedProject={selectedProject} />
        )}

        {activeTab === 'issues' && (
          <IssuesTab selectedProject={selectedProject} />
        )}

        {activeTab === 'status' && (
          <StatusTab selectedProject={selectedProject} />
        )}

        {activeTab === 'terminal' && debugOpen && (
          <DebugLogViewer
            selectedProject={selectedProject}
            height={debugPanelHeight}
            onHeightChange={onDebugHeightChange}
            activeTab={debugActiveTab}
            onTabChange={onDebugTabChange}
          />
        )}

        {activeTab === 'terminal' && !debugOpen && (
          <div className="flex items-center justify-center h-full text-gray-500">
            <div className="text-center">
              <p className="text-lg mb-2">Terminal panel is closed</p>
              <p className="text-sm">Press 'D' to open debug panel</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
