/**
 * UAT Report Exporter Component
 *
 * Provides UI for generating and exporting UAT test reports.
 * Supports multiple formats: HTML, PDF, JSON, CSV, Markdown.
 */

import { useState } from 'react'
import {
  Download,
  FileText,
  FileJson,
  FileSpreadsheet,
  Eye,
  Loader2
} from 'lucide-react'

export type ReportFormat = 'html' | 'pdf' | 'json' | 'csv' | 'markdown'

export interface ReportFormatOption {
  value: ReportFormat
  label: string
  description: string
  icon: React.ElementType
  extension: string
}

const REPORT_FORMATS: ReportFormatOption[] = [
  {
    value: 'html',
    label: 'HTML Report',
    description: 'Interactive HTML document with styling',
    icon: FileText,
    extension: 'html'
  },
  {
    value: 'pdf',
    label: 'PDF Document',
    description: 'Printable PDF format',
    icon: FileText,
    extension: 'pdf'
  },
  {
    value: 'json',
    label: 'JSON Data',
    description: 'Machine-readable JSON format',
    icon: FileJson,
    extension: 'json'
  },
  {
    value: 'csv',
    label: 'CSV Spreadsheet',
    description: 'For Excel and spreadsheet applications',
    icon: FileSpreadsheet,
    extension: 'csv'
  },
  {
    value: 'markdown',
    label: 'Markdown',
    description: 'Plain text Markdown format',
    icon: FileText,
    extension: 'md'
  }
]

interface UATReportExporterProps {
  cycleId: string
  cycleName?: string
  onClose?: () => void
}

export function UATReportExporter({ cycleId, cycleName, onClose }: UATReportExporterProps) {
  const [selectedFormat, setSelectedFormat] = useState<ReportFormat>('html')
  const [includeDetails, setIncludeDetails] = useState(true)
  const [includeFailures, setIncludeFailures] = useState(true)
  const [includeScreenshots, setIncludeScreenshots] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [showPreview, setShowPreview] = useState(false)

  const handleGenerate = async (preview = false) => {
    setIsGenerating(true)

    try {
      const response = await fetch('/api/uat/reports/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cycle_id: cycleId,
          format: selectedFormat,
          include_details: includeDetails,
          include_failures: includeFailures,
          include_screenshots: includeScreenshots,
          title: cycleName
        })
      })

      if (!response.ok) {
        throw new Error('Failed to generate report')
      }

      if (preview) {
        // For preview, show in modal
        setShowPreview(true)
      } else {
        // For download, get the blob and trigger download
        const content = await response.text()
        const format = REPORT_FORMATS.find(f => f.value === selectedFormat)
        const filename = `uat-report-${cycleId}-${new Date().toISOString().slice(0, 10)}.${format?.extension || 'txt'}`

        const blob = new Blob([content], {
          type: response.headers.get('content-type') || 'text/plain'
        })

        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)

        onClose?.()
      }
    } catch (error) {
      console.error('Error generating report:', error)
      alert('Failed to generate report. Please try again.')
    } finally {
      setIsGenerating(false)
    }
  }

  const selectedFormatInfo = REPORT_FORMATS.find(f => f.value === selectedFormat)
  const FormatIcon = selectedFormatInfo?.icon || FileText

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Export UAT Report
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
          Generate a comprehensive test report for cycle <code className="px-1 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">{cycleId}</code>
        </p>
      </div>

      {/* Format Selection */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Report Format
        </label>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {REPORT_FORMATS.map(format => {
            const Icon = format.icon
            const isSelected = selectedFormat === format.value

            return (
              <button
                key={format.value}
                onClick={() => setSelectedFormat(format.value)}
                className={`
                  p-4 border-2 rounded-lg text-left transition-all duration-200
                  ${isSelected
                    ? 'border-purple-500 bg-purple-50 dark:bg-purple-900/20'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                  }
                `}
              >
                <div className="flex items-start gap-3">
                  <Icon className={`w-5 h-5 mt-0.5 ${isSelected ? 'text-purple-600 dark:text-purple-400' : 'text-gray-400'}`} />
                  <div className="flex-1">
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {format.label}
                    </div>
                    <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                      {format.description}
                    </div>
                  </div>
                  {isSelected && (
                    <div className="w-2 h-2 rounded-full bg-purple-500 mt-2" />
                  )}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Options */}
      <div className="space-y-3">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Report Options
        </label>

        <label className="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800">
          <input
            type="checkbox"
            checked={includeDetails}
            onChange={(e) => setIncludeDetails(e.target.checked)}
            className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">
            Include detailed test results
          </span>
        </label>

        <label className="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800">
          <input
            type="checkbox"
            checked={includeFailures}
            onChange={(e) => setIncludeFailures(e.target.checked)}
            className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">
            Include failure details and stack traces
          </span>
        </label>

        <label className="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800">
          <input
            type="checkbox"
            checked={includeScreenshots}
            onChange={(e) => setIncludeScreenshots(e.target.checked)}
            className="w-4 h-4 text-purple-600 rounded focus:ring-purple-500"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">
            Include screenshots (may increase file size)
          </span>
        </label>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <button
          onClick={() => handleGenerate(false)}
          disabled={isGenerating}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors"
        >
          {isGenerating ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Generating...
            </>
          ) : (
            <>
              <Download className="w-4 h-4" />
              Download Report
            </>
          )}
        </button>

        {selectedFormat === 'html' && (
          <button
            onClick={() => handleGenerate(true)}
            disabled={isGenerating}
            className="px-4 py-2.5 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 font-medium rounded-lg transition-colors"
          >
            <Eye className="w-4 h-4 inline mr-1" />
            Preview
          </button>
        )}
      </div>

      {/* Preview Modal */}
      {showPreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Report Preview
              </h3>
              <button
                onClick={() => setShowPreview(false)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
              >
                ✕
              </button>
            </div>
            <div className="p-4 overflow-y-auto max-h-[calc(90vh-60px)]">
              <iframe
                src={`/api/uat/reports/preview?cycle_id=${cycleId}`}
                className="w-full h-[70vh] border border-gray-200 dark:border-gray-700 rounded"
                title="Report Preview"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default UATReportExporter
