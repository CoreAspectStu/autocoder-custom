/**
 * Results Modal Component
 *
 * Modal dialog for displaying detailed UAT test results with:
 * - Tabs for different test types
 * - Expandable result sections
 * - Visual diff comparison slider
 * - Accessibility violation details
 * - API request/response details
 * - Actions: retry, approve, export
 */

import { useState, useRef } from 'react'
import {
  X,
  Download,
  RefreshCw,
  CheckCircle,
  XCircle,
  Eye,
  AlertTriangle,
  FileText,
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink
} from 'lucide-react'
import { UATTestResult, UATTestType } from './UATCard'

// ============================================================================
// Types
// ============================================================================

interface ResultsModalProps {
  isOpen: boolean
  onClose: () => void
  result: UATTestResult
  onRetry?: () => void
  onApprove?: () => void
  onExport?: () => void
}

type TabType = 'overview' | 'visual' | 'a11y' | 'api' | 'logs'

interface ViolationDetails {
  rule_id: string
  impact: string
  description: string
  help_url: string
  wcag_tags: string[]
  selectors: string[]
  count: number
}

// ============================================================================
// Components
// ============================================================================

export function ResultsModal({
  isOpen,
  onClose,
  result,
  onRetry,
  onApprove,
  onExport
}: ResultsModalProps) {
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set())
  const [visualSliderPosition, setVisualSliderPosition] = useState(50)
  const [selectedImage, setSelectedImage] = useState<'baseline' | 'current' | 'diff'>('baseline')

  if (!isOpen) return null

  const toggleSection = (section: string) => {
    setExpandedSections(prev => {
      const newSet = new Set(prev)
      if (newSet.has(section)) {
        newSet.delete(section)
      } else {
        newSet.add(section)
      }
      return newSet
    })
  }

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    console.log(`Copied ${label} to clipboard`)
  }

  const availableTabs = (): TabType[] => {
    const tabs: TabType[] = ['overview', 'logs']

    if (result.test_type === 'visual' || result.test_type === 'comprehensive') {
      tabs.push('visual')
    }

    if (result.test_type === 'a11y' || result.test_type === 'comprehensive') {
      tabs.push('a11y')
    }

    if (result.test_type === 'api' || result.test_type === 'comprehensive') {
      tabs.push('api')
    }

    return tabs
  }

  const getTabIcon = (tab: TabType) => {
    const icons = {
      overview: FileText,
      visual: Eye,
      a11y: AlertTriangle,
      api: FileText,
      logs: FileText
    }
    const Icon = icons[tab] || FileText
    return <Icon className="w-4 h-4" />
  }

  const getStatusColor = (status: string) => {
    const colors = {
      passed: 'text-green-600',
      failed: 'text-red-600',
      running: 'text-blue-600',
      pending: 'text-gray-600'
    }
    return colors[status as keyof typeof colors] || 'text-gray-600'
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${
              result.status === 'passed'
                ? 'bg-green-100 dark:bg-green-900/30'
                : result.status === 'failed'
                ? 'bg-red-100 dark:bg-red-900/30'
                : 'bg-blue-100 dark:bg-blue-900/30'
            }`}>
              {result.status === 'passed' ? (
                <CheckCircle className="w-6 h-6 text-green-600 dark:text-green-400" />
              ) : result.status === 'failed' ? (
                <XCircle className="w-6 h-6 text-red-600 dark:text-red-400" />
              ) : (
                <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              )}
            </div>

            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                {result.test_name}
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {result.test_type === 'comprehensive' ? 'Comprehensive UAT Test' :
                 result.test_type === 'visual' ? 'Visual Regression Test' :
                 result.test_type === 'a11y' ? 'Accessibility Test' : 'API Test'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {onRetry && result.status === 'failed' && (
              <button
                onClick={onRetry}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                title="Retry test"
              >
                <RefreshCw className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </button>
            )}
            {onApprove && result.status === 'passed' && (
              <button
                onClick={onApprove}
                className="p-2 hover:bg-green-100 dark:hover:bg-green-900/30 rounded-lg transition-colors"
                title="Approve results"
              >
                <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
              </button>
            )}
            {onExport && (
              <button
                onClick={onExport}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                title="Export results"
              >
                <Download className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <X className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 dark:border-gray-700 px-6">
          {availableTabs().map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-3 font-medium text-sm border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-purple-500 text-purple-600 dark:text-purple-400'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100'
              }`}
            >
              <div className="flex items-center gap-2">
                {getTabIcon(tab)}
                <span className="capitalize">{tab}</span>
              </div>
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'overview' && (
            <OverviewTab
              result={result}
              expandedSections={expandedSections}
              toggleSection={toggleSection}
              copyToClipboard={copyToClipboard}
              getStatusColor={getStatusColor}
            />
          )}

          {activeTab === 'visual' && result.visual_diff && (
            <VisualTab
              visualDiff={result.visual_diff}
              sliderPosition={visualSliderPosition}
              onSliderChange={setVisualSliderPosition}
              selectedImage={selectedImage}
              onImageSelect={setSelectedImage}
              copyToClipboard={copyToClipboard}
            />
          )}

          {activeTab === 'a11y' && result.a11y_violations && (
            <A11yTab
              violations={result.a11y_violations}
              expandedSections={expandedSections}
              toggleSection={toggleSection}
              copyToClipboard={copyToClipboard}
            />
          )}

          {activeTab === 'api' && result.api_results && (
            <APITab
              apiResults={result.api_results}
              expandedSections={expandedSections}
              toggleSection={toggleSection}
              copyToClipboard={copyToClipboard}
            />
          )}

          {activeTab === 'logs' && (
            <LogsTab
              result={result}
              copyToClipboard={copyToClipboard}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
          <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
            {result.started_at && (
              <span>Started: {new Date(result.started_at).toLocaleString()}</span>
            )}
            {result.completed_at && (
              <span>Completed: {new Date(result.completed_at).toLocaleString()}</span>
            )}
            {result.duration_seconds && (
              <span>Duration: {Math.floor(result.duration_seconds / 60)}m {result.duration_seconds % 60}s</span>
            )}
          </div>

          <button
            onClick={onClose}
            className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Tab Components
// ============================================================================

function OverviewTab({
  result,
  expandedSections,
  toggleSection,
  copyToClipboard,
  getStatusColor
}: {
  result: UATTestResult
  expandedSections: Set<string>
  toggleSection: (section: string) => void
  copyToClipboard: (text: string, label: string) => void
  getStatusColor: (status: string) => string
}) {
  const sections = [
    { id: 'summary', title: 'Summary', alwaysExpanded: true },
    { id: 'details', title: 'Test Details', alwaysExpanded: false },
    { id: 'scores', title: 'Scores & Metrics', alwaysExpanded: false },
  ]

  return (
    <div className="space-y-4">
      {sections.map((section) => {
        const isExpanded = section.alwaysExpanded || expandedSections.has(section.id)

        return (
          <div key={section.id} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <button
              onClick={() => toggleSection(section.id)}
              className="w-full flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <h3 className="font-semibold text-gray-900 dark:text-gray-100">{section.title}</h3>
              {!section.alwaysExpanded && (
                <ChevronDown className={`w-4 h-4 text-gray-600 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
              )}
            </button>

            {isExpanded && (
              <div className="p-4 space-y-4">
                {section.id === 'summary' && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-3 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
                        <p className="text-sm text-gray-600 dark:text-gray-400">Status</p>
                        <p className={`text-lg font-semibold ${getStatusColor(result.status)}`}>
                          {result.status.charAt(0).toUpperCase() + result.status.slice(1)}
                        </p>
                      </div>

                      {result.score !== undefined && (
                        <div className="p-3 bg-white dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700">
                          <p className="text-sm text-gray-600 dark:text-gray-400">Score</p>
                          <p className={`text-lg font-semibold ${
                            result.score >= 90 ? 'text-green-600' : result.score >= 70 ? 'text-yellow-600' : 'text-red-600'
                          }`}>
                            {result.score}%
                          </p>
                        </div>
                      )}
                    </div>
                  </>
                )}

                {section.id === 'details' && (
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between p-2 bg-white dark:bg-gray-800 rounded">
                      <span className="text-gray-600 dark:text-gray-400">Test ID</span>
                      <span className="font-mono text-gray-900 dark:text-gray-100">{result.test_id}</span>
                    </div>
                    <div className="flex justify-between p-2 bg-white dark:bg-gray-800 rounded">
                      <span className="text-gray-600 dark:text-gray-400">Test Type</span>
                      <span className="text-gray-900 dark:text-gray-100">{result.test_type}</span>
                    </div>
                    {result.report_path && (
                      <div className="flex justify-between p-2 bg-white dark:bg-gray-800 rounded">
                        <span className="text-gray-600 dark:text-gray-400">Report Path</span>
                        <span className="text-gray-900 dark:text-gray-100 truncate ml-4">{result.report_path}</span>
                      </div>
                    )}
                  </div>
                )}

                {section.id === 'scores' && (
                  <div className="space-y-2">
                    {result.a11y_violations && (
                      <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded">
                        <p className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">
                          Accessibility Violations
                        </p>
                        <div className="grid grid-cols-2 gap-2 text-sm">
                          <span>Critical: {result.a11y_violations.critical}</span>
                          <span>Serious: {result.a11y_violations.serious}</span>
                          <span>Moderate: {result.a11y_violations.moderate}</span>
                          <span>Minor: {result.a11y_violations.minor}</span>
                        </div>
                      </div>
                    )}

                    {result.visual_diff && result.visual_diff.diff_percentage !== undefined && (
                      <div className="p-3 bg-purple-50 dark:bg-purple-900/20 rounded">
                        <p className="text-sm font-medium text-purple-900 dark:text-purple-100 mb-2">
                          Visual Difference
                        </p>
                        <p className="text-sm text-purple-700 dark:text-purple-300">
                          {result.visual_diff.diff_percentage.toFixed(1)}% difference detected
                        </p>
                      </div>
                    )}

                    {result.api_results && (
                      <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded">
                        <p className="text-sm font-medium text-green-900 dark:text-green-100 mb-2">
                          API Test Results
                        </p>
                        <div className="text-sm space-y-1">
                          <p>Endpoints: {result.api_results.endpoints_tested}</p>
                          <p>Passed: {result.api_results.passed} / Failed: {result.api_results.failed}</p>
                          <p>Avg Response: {result.api_results.avg_response_time_ms}ms</p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function VisualTab({
  visualDiff,
  sliderPosition,
  onSliderChange,
  selectedImage,
  onImageSelect,
  copyToClipboard
}: {
  visualDiff: NonNullable<UATTestResult['visual_diff']>
  sliderPosition: number
  onSliderChange: (pos: number) => void
  selectedImage: 'baseline' | 'current' | 'diff'
  onImageSelect: (img: 'baseline' | 'current' | 'diff') => void
  copyToClipboard: (text: string, label: string) => void
}) {
  return (
    <div className="space-y-4">
      {/* Image Comparison Slider */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Visual Comparison
        </h3>

        {/* Image Selector */}
        <div className="flex gap-2 mb-4">
          {(['baseline', 'current', 'diff'] as const).map((img) => (
            <button
              key={img}
              onClick={() => onImageSelect(img)}
              className={`px-3 py-1 text-sm rounded border-2 transition-colors ${
                selectedImage === img
                  ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20 text-purple-600'
                  : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400'
              }`}
            >
              {img.charAt(0).toUpperCase() + img.slice(1)}
            </button>
          ))}
        </div>

        {/* Slider */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Comparison Slider: {Math.round(sliderPosition)}%
          </label>
          <input
            type="range"
            min="0"
            max="100"
            value={sliderPosition}
            onChange={(e) => onSliderChange(parseInt(e.target.value))}
            className="w-full"
          />
        </div>

        {/* Image Display */}
        <div className="relative aspect-video bg-gray-100 dark:bg-gray-800 rounded border border-gray-300 dark:border-gray-600 flex items-center justify-center">
          {selectedImage === 'baseline' && visualDiff.baseline_path && (
            <img
              src={visualDiff.baseline_path}
              alt="Baseline"
              className="max-w-full max-h-full object-contain"
            />
          )}
          {selectedImage === 'current' && visualDiff.current_path && (
            <img
              src={visualDiff.current_path}
              alt="Current"
              className="max-w-full max-h-full object-contain"
            />
          )}
          {selectedImage === 'diff' && visualDiff.diff_path && (
            <img
              src={visualDiff.diff_path}
              alt="Diff"
              className="max-w-full max-h-full object-contain"
            />
          )}
          {!visualDiff.baseline_path && !visualDiff.current_path && !visualDiff.diff_path && (
            <p className="text-gray-500">No image available</p>
          )}
        </div>
      </div>

      {/* Diff Details */}
      {visualDiff.diff_percentage !== undefined && (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Diff Analysis
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-gray-600 dark:text-gray-400">Difference</p>
              <p className="text-lg font-semibold text-purple-600">
                {visualDiff.diff_percentage.toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-gray-600 dark:text-gray-400">Status</p>
              <p className={`text-lg font-semibold ${
                visualDiff.diff_percentage < 5 ? 'text-green-600' :
                visualDiff.diff_percentage < 10 ? 'text-yellow-600' : 'text-red-600'
              }`}>
                {visualDiff.diff_percentage < 5 ? 'Pass' : visualDiff.diff_percentage < 10 ? 'Warning' : 'Fail'}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function A11yTab({
  violations,
  expandedSections,
  toggleSection,
  copyToClipboard
}: {
  violations: NonNullable<UATTestResult['a11y_violations']>
  expandedSections: Set<string>
  toggleSection: (section: string) => void
  copyToClipboard: (text: string, label: string) => void
}) {
  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-4 gap-4">
        <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg text-center">
          <p className="text-2xl font-bold text-red-600 dark:text-red-400">{violations.critical}</p>
          <p className="text-sm text-red-700 dark:text-red-300">Critical</p>
        </div>
        <div className="p-4 bg-orange-50 dark:bg-orange-900/20 rounded-lg text-center">
          <p className="text-2xl font-bold text-orange-600 dark:text-orange-400">{violations.serious}</p>
          <p className="text-sm text-orange-700 dark:text-orange-300">Serious</p>
        </div>
        <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg text-center">
          <p className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">{violations.moderate}</p>
          <p className="text-sm text-yellow-700 dark:text-yellow-300">Moderate</p>
        </div>
        <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg text-center">
          <p className="text-2xl font-bold text-gray-600 dark:text-gray-400">{violations.minor}</p>
          <p className="text-sm text-gray-700 dark:text-gray-300">Minor</p>
        </div>
      </div>

      {/* WCAG Compliance */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
          WCAG Compliance Summary
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Total violations: {violations.total}
        </p>
      </div>

      {/* Common Violations */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
          Common Violations
        </h3>
        <div className="space-y-2">
          {violations.critical > 0 && (
            <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-700 dark:text-red-300">
                {violations.critical} critical violation{violations.critical > 1 ? 's' : ''} must be fixed
              </p>
            </div>
          )}
          {violations.serious > 0 && (
            <div className="p-3 bg-orange-50 dark:bg-orange-900/20 rounded flex items-start gap-2">
              <AlertTriangle className="w-5 h-5 text-orange-600 dark:text-orange-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-orange-700 dark:text-orange-300">
                {violations.serious} serious violation{violations.serious > 1 ? 's' : ''} should be addressed
              </p>
            </div>
          )}
          {violations.total === 0 && (
            <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
              <p className="text-sm text-green-700 dark:text-green-300">
                No accessibility violations detected!
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function APITab({
  apiResults,
  expandedSections,
  toggleSection,
  copyToClipboard
}: {
  apiResults: NonNullable<UATTestResult['api_results']>
  expandedSections: Set<string>
  toggleSection: (section: string) => void
  copyToClipboard: (text: string, label: string) => void
}) {
  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid grid-cols-4 gap-4">
        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-center">
          <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
            {apiResults.endpoints_tested}
          </p>
          <p className="text-sm text-blue-700 dark:text-blue-300">Endpoints</p>
        </div>
        <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg text-center">
          <p className="text-2xl font-bold text-green-600 dark:text-green-400">{apiResults.passed}</p>
          <p className="text-sm text-green-700 dark:text-green-300">Passed</p>
        </div>
        <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg text-center">
          <p className="text-2xl font-bold text-red-600 dark:text-red-400">{apiResults.failed}</p>
          <p className="text-sm text-red-700 dark:text-red-300">Failed</p>
        </div>
        <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg text-center">
          <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
            {apiResults.avg_response_time_ms}ms
          </p>
          <p className="text-sm text-purple-700 dark:text-purple-300">Avg Time</p>
        </div>
      </div>

      {/* Pass Rate */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
          Pass Rate
        </h3>
        <div className="relative pt-1">
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4">
            <div
              className="bg-green-500 h-4 rounded-full transition-all duration-300"
              style={{ width: `${(apiResults.passed / apiResults.endpoints_tested) * 100}%` }}
            />
          </div>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
          {((apiResults.passed / apiResults.endpoints_tested) * 100).toFixed(1)}%
        </p>
      </div>

      {/* Performance */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
          Performance Metrics
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Average response time: <span className="font-mono">{apiResults.avg_response_time_ms}ms</span>
        </p>
      </div>
    </div>
  )
}

function LogsTab({
  result,
  copyToClipboard
}: {
  result: UATTestResult
  copyToClipboard: (text: string, label: string) => void
}) {
  const logLines = [
    `[${result.started_at}] Starting UAT test: ${result.test_name}`,
    `[${result.started_at}] Test type: ${result.test_type}`,
    `[${result.started_at}] Test ID: ${result.test_id}`,
    ``,
    `[${result.completed_at}] Test completed with status: ${result.status}`,
    result.score !== undefined && `[${result.completed_at}] Final score: ${result.score}%`,
    result.duration_seconds && `[${result.completed_at}] Duration: ${result.duration_seconds}s`,
    result.error && `[${result.completed_at}] Error: ${result.error}`,
    ``,
    `[${result.completed_at}] Report path: ${result.report_path || 'N/A'}`
  ].filter(Boolean)

  return (
    <div className="space-y-4">
      {/* Log Actions */}
      <div className="flex justify-end">
        <button
          onClick={() => copyToClipboard(logLines.join('\n'), 'logs')}
          className="flex items-center gap-2 px-3 py-1 text-sm bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors"
        >
          <Copy className="w-4 h-4" />
          Copy Logs
        </button>
      </div>

      {/* Log Content */}
      <div className="bg-gray-900 dark:bg-gray-950 rounded-lg p-4 font-mono text-sm">
        <pre className="text-gray-100 whitespace-pre-wrap">{logLines.join('\n')}</pre>
      </div>
    </div>
  )
}

export default ResultsModal
