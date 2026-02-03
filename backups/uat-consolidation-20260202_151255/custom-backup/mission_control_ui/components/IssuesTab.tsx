import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bug, Lightbulb, AlertCircle, StickyNote, Plus, Check, Loader2, X } from 'lucide-react'

interface Annotation {
  id: string
  project: string
  feature_id: string | null
  type: 'bug' | 'idea' | 'workaround' | 'comment'
  content: string
  created_at: string
  resolved: number // 0 or 1 (SQLite boolean)
}

interface IssuesTabProps {
  selectedProject: string | null
}

const ANNOTATION_TYPES = [
  { id: 'bug', label: 'Bug', icon: Bug, color: 'red' },
  { id: 'idea', label: 'Idea', icon: Lightbulb, color: 'purple' },
  { id: 'workaround', label: 'Workaround', icon: AlertCircle, color: 'orange' },
  { id: 'comment', label: 'Comment', icon: StickyNote, color: 'blue' },
] as const

export function IssuesTab({ selectedProject }: IssuesTabProps) {
  const [showAddForm, setShowAddForm] = useState(false)
  const [newType, setNewType] = useState<'bug' | 'idea' | 'workaround' | 'comment'>('bug')
  const [newContent, setNewContent] = useState('')
  const [filterResolved, setFilterResolved] = useState(false)
  const queryClient = useQueryClient()

  // Fetch annotations for selected project
  const { data: annotations = [], isLoading } = useQuery<Annotation[]>({
    queryKey: ['devlayer', 'annotations', selectedProject],
    queryFn: async () => {
      if (!selectedProject) return []
      const res = await fetch(`/api/devlayer/projects/${encodeURIComponent(selectedProject)}/annotations`)
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!selectedProject,
    refetchInterval: 5000,
  })

  // Create annotation
  const createAnnotation = useMutation({
    mutationFn: async (data: { type: string; content: string }) => {
      if (!selectedProject) throw new Error('No project selected')
      const res = await fetch(`/api/devlayer/projects/${encodeURIComponent(selectedProject)}/annotations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
      if (!res.ok) throw new Error('Failed to create annotation')
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devlayer', 'annotations', selectedProject] })
      setNewContent('')
      setShowAddForm(false)
    }
  })

  // Mark as resolved/unresolved
  const toggleResolved = useMutation({
    mutationFn: async (annotation: Annotation) => {
      const res = await fetch(`/api/devlayer/annotations/${annotation.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved: annotation.resolved === 1 ? 0 : 1 })
      })
      if (!res.ok) throw new Error('Failed to update annotation')
      return res.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devlayer', 'annotations', selectedProject] })
    }
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (newContent.trim() && !createAnnotation.isPending) {
      createAnnotation.mutate({ type: newType, content: newContent.trim() })
    }
  }

  const filteredAnnotations = annotations.filter(ann =>
    filterResolved ? ann.resolved === 1 : ann.resolved === 0
  )

  const getTypeConfig = (type: string) => {
    return ANNOTATION_TYPES.find(t => t.id === type) || ANNOTATION_TYPES[0]
  }

  if (!selectedProject) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <div className="text-center">
          <p className="text-lg mb-2">No project selected</p>
          <p className="text-sm">Select a project to view issues</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Issues & Annotations
            </h2>
            <p className="text-sm text-gray-500">
              {filteredAnnotations.length} {filterResolved ? 'resolved' : 'active'} items
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Filter Toggle */}
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={filterResolved}
                onChange={(e) => setFilterResolved(e.target.checked)}
                className="rounded border-gray-300"
              />
              Show resolved
            </label>

            {/* Add Button */}
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className="neo-btn px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 flex items-center gap-2"
            >
              {showAddForm ? <X size={18} /> : <Plus size={18} />}
              {showAddForm ? 'Cancel' : 'Add Issue'}
            </button>
          </div>
        </div>

        {/* Add Form */}
        {showAddForm && (
          <form onSubmit={handleSubmit} className="mt-4 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="space-y-3">
              {/* Type Selector */}
              <div className="flex gap-2">
                {ANNOTATION_TYPES.map((type) => (
                  <button
                    key={type.id}
                    type="button"
                    onClick={() => setNewType(type.id)}
                    className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      newType === type.id
                        ? `bg-${type.color}-500 text-white`
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                    }`}
                  >
                    <type.icon size={16} className="inline mr-1" />
                    {type.label}
                  </button>
                ))}
              </div>

              {/* Content Input */}
              <textarea
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder={`Describe the ${newType}...`}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />

              {/* Submit Button */}
              <button
                type="submit"
                disabled={!newContent.trim() || createAnnotation.isPending}
                className="neo-btn px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {createAnnotation.isPending ? (
                  <Loader2 className="animate-spin" size={18} />
                ) : (
                  <Plus size={18} />
                )}
                Add {newType}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Annotations List */}
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="animate-spin text-gray-400" size={32} />
          </div>
        )}

        {!isLoading && filteredAnnotations.length === 0 && (
          <div className="text-center text-gray-500 py-8">
            <p className="text-lg mb-2">No {filterResolved ? 'resolved' : 'active'} issues</p>
            <p className="text-sm">Click "Add Issue" to create one</p>
          </div>
        )}

        <div className="space-y-3">
          {filteredAnnotations.map((annotation) => {
            const typeConfig = getTypeConfig(annotation.type)
            const Icon = typeConfig.icon

            return (
              <div
                key={annotation.id}
                className={`p-4 rounded-lg border-l-4 bg-white dark:bg-gray-800 border-${typeConfig.color}-500 shadow-sm`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <Icon size={18} className={`text-${typeConfig.color}-500`} />
                      <span className={`text-sm font-medium text-${typeConfig.color}-600 dark:text-${typeConfig.color}-400`}>
                        {typeConfig.label}
                      </span>
                      <span className="text-xs text-gray-500">
                        {new Date(annotation.created_at).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </span>
                    </div>
                    <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">
                      {annotation.content}
                    </p>
                  </div>

                  {/* Resolve Toggle */}
                  <button
                    onClick={() => toggleResolved.mutate(annotation)}
                    disabled={toggleResolved.isPending}
                    className={`p-2 rounded-lg transition-colors ${
                      annotation.resolved === 1
                        ? 'bg-green-100 text-green-600 hover:bg-green-200'
                        : 'bg-gray-100 text-gray-400 hover:bg-gray-200'
                    }`}
                    title={annotation.resolved === 1 ? 'Mark as unresolved' : 'Mark as resolved'}
                  >
                    <Check size={18} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
