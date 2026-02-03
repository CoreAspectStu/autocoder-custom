/**
 * UAT CI/CD Integration Component
 *
 * Configuration UI for integrating UAT tests with CI/CD pipelines.
 * Supports GitHub Actions, Jenkins, GitLab CI, and webhooks.
 */

import { useState } from 'react'
import {
  Github,
  RefreshCw,
  Webhook,
  Key,
  Check,
  Copy,
  Settings
} from 'lucide-react'

export type CIProvider = 'github' | 'gitlab' | 'jenkins' | 'webhook' | 'azure-devops'

export interface CIConfig {
  id: string
  provider: CIProvider
  name: string
  project: string
  branch: string
  webhook_url: string
  secret?: string
  enabled: boolean
  config: Record<string, any>
}

interface UATCICDIntegrationProps {
  projectId: string
  onConfigSave?: (config: CIConfig) => void
}

const PROVIDER_OPTIONS = [
  {
    value: 'github',
    label: 'GitHub Actions',
    icon: Github,
    description: 'Trigger tests from GitHub Actions workflows',
    color: 'text-gray-900 dark:text-gray-100'
  },
  {
    value: 'gitlab',
    label: 'GitLab CI',
    icon: Settings,
    description: 'Integrate with GitLab CI/CD pipelines',
    color: 'text-orange-600 dark:text-orange-400'
  },
  {
    value: 'jenkins',
    label: 'Jenkins',
    icon: Settings,
    description: 'Trigger from Jenkins build jobs',
    color: 'text-red-600 dark:text-red-400'
  },
  {
    value: 'azure-devops',
    label: 'Azure DevOps',
    icon: Settings,
    description: 'Azure Pipelines integration',
    color: 'text-blue-600 dark:text-blue-400'
  },
  {
    value: 'webhook',
    label: 'Generic Webhook',
    icon: Webhook,
    description: 'Use webhook URL for custom integrations',
    color: 'text-purple-600 dark:text-purple-400'
  }
]

export function UATCICDIntegration({ projectId, onConfigSave }: UATCICDIntegrationProps) {
  const [configs, setConfigs] = useState<CIConfig[]>([])
  const [showForm, setShowForm] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState<CIProvider>('github')
  const [copiedWebhook, setCopiedWebhook] = useState<string | null>(null)

  const [formData, setFormData] = useState({
    name: '',
    project: '',
    branch: 'main',
    secret: '',
    enabled: true
  })

  // Generate webhook URL
  const webhookUrl = `${window.location.origin}/api/uat/webhook/ci/${projectId}`

  const handleSave = () => {
    const config: CIConfig = {
      id: `ci-${Date.now()}`,
      provider: selectedProvider,
      name: formData.name || `${selectedProvider} integration`,
      project: formData.project,
      branch: formData.branch,
      webhook_url: webhookUrl,
      secret: formData.secret || undefined,
      enabled: formData.enabled,
      config: {}
    }

    setConfigs(prev => [...prev, config])
    onConfigSave?.(config)
    setShowForm(false)
    resetForm()
  }

  const handleDelete = (id: string) => {
    setConfigs(prev => prev.filter(c => c.id !== id))
  }

  const handleCopyWebhook = (url: string, id: string) => {
    navigator.clipboard.writeText(url)
    setCopiedWebhook(id)
    setTimeout(() => setCopiedWebhook(null), 2000)
  }

  const resetForm = () => {
    setFormData({
      name: '',
      project: '',
      branch: 'main',
      secret: '',
      enabled: true
    })
  }

  const generateWorkflowYaml = () => {
    const secret = formData.secret ? 'YOUR_SECRET_HERE' : 'YOUR_SECRET_HERE'
    const project = formData.project || 'your-project'

    if (selectedProvider === 'github') {
      return `name: UAT Tests

on:
  push:
    branches: [ ${formData.branch} ]
  pull_request:
    branches: [ ${formData.branch} ]

jobs:
  uat:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger UAT Tests
        run: |
          curl -X POST ${webhookUrl} \\\\
            -H "Content-Type: application/json" \\\\
            -H "X-UAT-Secret: ${secret}" \\\\
            -d '{\\'event\\':\\'run_uat\\',\\'project\\':\\'${project}\\'}'
`
    }

    if (selectedProvider === 'gitlab') {
      return `uat_tests:
  stage: test
  script:
    - curl -X POST ${webhookUrl} \\\\
      -H "Content-Type: application/json" \\\\
      -H "X-UAT-Secret: ${secret}" \\\\
      -d '{\\'event\\':\\'run_uat\\'}'
  only:
    - ${formData.branch}
`
    }

    if (selectedProvider === 'jenkins') {
      return `pipeline {
    agent any
    stages {
        stage('UAT Tests') {
            steps {
                sh 'curl -X POST ${webhookUrl} -H "Content-Type: application/json" -d "{\\'event\\':\\'run_uat\\'}"'
            }
        }
    }
}`
    }

    return '# Webhook URL: ' + webhookUrl
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            CI/CD Integration
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Connect your UAT tests to CI/CD pipelines
          </p>
        </div>
      </div>

      {/* Webhook URL */}
      <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Webhook URL
        </label>
        <div className="flex items-center gap-2">
          <code className="flex-1 px-3 py-2 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-mono">
            {webhookUrl}
          </code>
          <button
            onClick={() => handleCopyWebhook(webhookUrl, 'main')}
            className="p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors"
            title="Copy webhook URL"
          >
            {copiedWebhook === 'main' ? (
              <Check className="w-4 h-4 text-green-600 dark:text-green-400" />
            ) : (
              <Copy className="w-4 h-4 text-gray-600 dark:text-gray-400" />
            )}
          </button>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
          Use this URL to trigger UAT tests from your CI/CD pipeline
        </p>
      </div>

      {/* Provider Selection */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Choose Integration Provider
        </label>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {PROVIDER_OPTIONS.map(provider => {
            const Icon = provider.icon
            return (
              <button
                key={provider.value}
                onClick={() => { setSelectedProvider(provider.value as CIProvider); setShowForm(true); }}
                className="p-4 border-2 border-gray-200 dark:border-gray-700 rounded-lg text-left hover:border-purple-500 dark:hover:border-purple-500 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <Icon className={`w-5 h-5 mt-0.5 ${provider.color}`} />
                  <div className="flex-1">
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {provider.label}
                    </div>
                    <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                      {provider.description}
                    </div>
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Active Integrations */}
      {configs.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
            Active Integrations
          </h4>
          <div className="space-y-3">
            {configs.map(config => {
              const provider = PROVIDER_OPTIONS.find(p => p.value === config.provider)
              const Icon = provider?.icon || Settings
              return (
                <div
                  key={config.id}
                  className="p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <Icon className={`w-5 h-5 mt-0.5 ${provider?.color}`} />
                      <div>
                        <h5 className="font-medium text-gray-900 dark:text-gray-100">
                          {config.name}
                        </h5>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                          {config.project} · {config.branch}
                        </p>
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full mt-2 ${
                          config.enabled
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                            : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'
                        }`}>
                          {config.enabled ? 'Active' : 'Paused'}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDelete(config.id)}
                      className="p-2 hover:bg-red-100 dark:hover:bg-red-900/20 rounded transition-colors"
                      title="Remove integration"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Integration Setup Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Setup {PROVIDER_OPTIONS.find(p => p.value === selectedProvider)?.label}
              </h3>
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-6">
              {/* Configuration Form */}
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Integration Name
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g., Production UAT"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Project / Repository
                  </label>
                  <input
                    type="text"
                    value={formData.project}
                    onChange={(e) => setFormData({ ...formData, project: e.target.value })}
                    placeholder="owner/repo or project name"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Branch
                  </label>
                  <input
                    type="text"
                    value={formData.branch}
                    onChange={(e) => setFormData({ ...formData, branch: e.target.value })}
                    placeholder="main"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Webhook Secret (optional)
                  </label>
                  <div className="flex items-center gap-2">
                    <Key className="w-4 h-4 text-gray-400" />
                    <input
                      type="password"
                      value={formData.secret}
                      onChange={(e) => setFormData({ ...formData, secret: e.target.value })}
                      placeholder="Generate a secure secret"
                      className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800"
                    />
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                    Leave empty to generate one automatically, or provide your own
                  </p>
                </div>
              </div>

              {/* Generated Workflow */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Generated Workflow Configuration
                </label>
                <div className="relative">
                  <pre className="p-4 bg-gray-900 text-gray-100 rounded-lg text-sm overflow-x-auto">
                    <code>{generateWorkflowYaml()}</code>
                  </pre>
                  <button
                    onClick={() => handleCopyWebhook(generateWorkflowYaml(), 'yaml')}
                    className="absolute top-2 right-2 p-2 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
                    title="Copy configuration"
                  >
                    {copiedWebhook === 'yaml' ? (
                      <Check className="w-4 h-4 text-green-400" />
                    ) : (
                      <Copy className="w-4 h-4 text-gray-300" />
                    )}
                  </button>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
                  Copy this to your CI/CD configuration file (e.g., .github/workflows/uat.yml)
                </p>
              </div>
            </div>

            <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
              <button
                onClick={() => setShowForm(false)}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg flex items-center gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                Save Integration
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default UATCICDIntegration
