/**
 * API Client for the Autonomous Coding UI
 */

import type {
  ProjectSummary,
  ProjectDetail,
  ProjectPrompts,
  FeatureListResponse,
  Feature,
  FeatureCreate,
  FeatureUpdate,
  FeatureBulkCreate,
  FeatureBulkCreateResponse,
  DependencyGraph,
  AgentStatusResponse,
  AgentActionResponse,
  SetupStatus,
  DirectoryListResponse,
  PathValidationResponse,
  AssistantConversation,
  AssistantConversationDetail,
  Settings,
  SettingsUpdate,
  ModelsResponse,
  DevServerStatusResponse,
  DevServerConfig,
  TerminalInfo,
  Schedule,
  ScheduleCreate,
  ScheduleUpdate,
  ScheduleListResponse,
  NextRunResponse,
} from './types'

const API_BASE = '/api'

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  // Handle 204 No Content responses
  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

// ============================================================================
// Projects API
// ============================================================================

export async function listProjects(): Promise<ProjectSummary[]> {
  return fetchJSON('/projects')
}

export async function createProject(
  name: string,
  path: string,
  specMethod: 'claude' | 'manual' = 'manual'
): Promise<ProjectSummary> {
  return fetchJSON('/projects', {
    method: 'POST',
    body: JSON.stringify({ name, path, spec_method: specMethod }),
  })
}

export async function getProject(name: string): Promise<ProjectDetail> {
  return fetchJSON(`/projects/${encodeURIComponent(name)}`)
}

export async function deleteProject(name: string): Promise<void> {
  await fetchJSON(`/projects/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

export async function getProjectPrompts(name: string): Promise<ProjectPrompts> {
  return fetchJSON(`/projects/${encodeURIComponent(name)}/prompts`)
}

export async function updateProjectPrompts(
  name: string,
  prompts: Partial<ProjectPrompts>
): Promise<void> {
  await fetchJSON(`/projects/${encodeURIComponent(name)}/prompts`, {
    method: 'PUT',
    body: JSON.stringify(prompts),
  })
}

// ============================================================================
// Features API
// ============================================================================

export async function listFeatures(projectName: string): Promise<FeatureListResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features`)
}

export async function createFeature(projectName: string, feature: FeatureCreate): Promise<Feature> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features`, {
    method: 'POST',
    body: JSON.stringify(feature),
  })
}

export async function getFeature(projectName: string, featureId: number): Promise<Feature> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/${featureId}`)
}

export async function deleteFeature(projectName: string, featureId: number): Promise<void> {
  await fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/${featureId}`, {
    method: 'DELETE',
  })
}

export async function skipFeature(projectName: string, featureId: number): Promise<void> {
  await fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/${featureId}/skip`, {
    method: 'PATCH',
  })
}

export async function updateFeature(
  projectName: string,
  featureId: number,
  update: FeatureUpdate
): Promise<Feature> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/${featureId}`, {
    method: 'PATCH',
    body: JSON.stringify(update),
  })
}

export async function createFeaturesBulk(
  projectName: string,
  bulk: FeatureBulkCreate
): Promise<FeatureBulkCreateResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/bulk`, {
    method: 'POST',
    body: JSON.stringify(bulk),
  })
}

// ============================================================================
// Dependency Graph API
// ============================================================================

export async function getDependencyGraph(projectName: string): Promise<DependencyGraph> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/features/graph`)
}

export async function addDependency(
  projectName: string,
  featureId: number,
  dependencyId: number
): Promise<{ success: boolean; feature_id: number; dependencies: number[] }> {
  return fetchJSON(
    `/projects/${encodeURIComponent(projectName)}/features/${featureId}/dependencies/${dependencyId}`,
    { method: 'POST' }
  )
}

export async function removeDependency(
  projectName: string,
  featureId: number,
  dependencyId: number
): Promise<{ success: boolean; feature_id: number; dependencies: number[] }> {
  return fetchJSON(
    `/projects/${encodeURIComponent(projectName)}/features/${featureId}/dependencies/${dependencyId}`,
    { method: 'DELETE' }
  )
}

export async function setDependencies(
  projectName: string,
  featureId: number,
  dependencyIds: number[]
): Promise<{ success: boolean; feature_id: number; dependencies: number[] }> {
  return fetchJSON(
    `/projects/${encodeURIComponent(projectName)}/features/${featureId}/dependencies`,
    {
      method: 'PUT',
      body: JSON.stringify({ dependency_ids: dependencyIds }),
    }
  )
}

// ============================================================================
// Agent API
// ============================================================================

export async function getAgentStatus(projectName: string): Promise<AgentStatusResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/status`)
}

export async function startAgent(
  projectName: string,
  options: {
    yoloMode?: boolean
    parallelMode?: boolean
    maxConcurrency?: number
    testingAgentRatio?: number
  } = {}
): Promise<AgentActionResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/start`, {
    method: 'POST',
    body: JSON.stringify({
      yolo_mode: options.yoloMode ?? false,
      parallel_mode: options.parallelMode ?? false,
      max_concurrency: options.maxConcurrency,
      testing_agent_ratio: options.testingAgentRatio,
    }),
  })
}

export async function stopAgent(projectName: string): Promise<AgentActionResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/stop`, {
    method: 'POST',
  })
}

export async function pauseAgent(projectName: string): Promise<AgentActionResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/pause`, {
    method: 'POST',
  })
}

export async function resumeAgent(projectName: string): Promise<AgentActionResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/agent/resume`, {
    method: 'POST',
  })
}

// ============================================================================
// Spec Creation API
// ============================================================================

export interface SpecFileStatus {
  exists: boolean
  status: 'complete' | 'in_progress' | 'not_started' | 'error' | 'unknown'
  feature_count: number | null
  timestamp: string | null
  files_written: string[]
}

export async function getSpecStatus(projectName: string): Promise<SpecFileStatus> {
  return fetchJSON(`/spec/status/${encodeURIComponent(projectName)}`)
}

// ============================================================================
// Setup API
// ============================================================================

export async function getSetupStatus(): Promise<SetupStatus> {
  return fetchJSON('/setup/status')
}

export async function healthCheck(): Promise<{ status: string }> {
  return fetchJSON('/health')
}

// ============================================================================
// Filesystem API
// ============================================================================

export async function listDirectory(path?: string): Promise<DirectoryListResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : ''
  return fetchJSON(`/filesystem/list${params}`)
}

export async function createDirectory(fullPath: string): Promise<{ success: boolean; path: string }> {
  // Backend expects { parent_path, name }, not { path }
  // Split the full path into parent directory and folder name

  // Remove trailing slash if present
  const normalizedPath = fullPath.endsWith('/') ? fullPath.slice(0, -1) : fullPath

  // Find the last path separator
  const lastSlash = normalizedPath.lastIndexOf('/')

  let parentPath: string
  let name: string

  // Handle Windows drive root (e.g., "C:/newfolder")
  if (lastSlash === 2 && /^[A-Za-z]:/.test(normalizedPath)) {
    // Path like "C:/newfolder" - parent is "C:/"
    parentPath = normalizedPath.substring(0, 3) // "C:/"
    name = normalizedPath.substring(3)
  } else if (lastSlash > 0) {
    parentPath = normalizedPath.substring(0, lastSlash)
    name = normalizedPath.substring(lastSlash + 1)
  } else if (lastSlash === 0) {
    // Unix root path like "/newfolder"
    parentPath = '/'
    name = normalizedPath.substring(1)
  } else {
    // No slash - invalid path
    throw new Error('Invalid path: must be an absolute path')
  }

  if (!name) {
    throw new Error('Invalid path: directory name is empty')
  }

  return fetchJSON('/filesystem/create-directory', {
    method: 'POST',
    body: JSON.stringify({ parent_path: parentPath, name }),
  })
}

export async function validatePath(path: string): Promise<PathValidationResponse> {
  return fetchJSON('/filesystem/validate', {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

// ============================================================================
// Assistant Chat API
// ============================================================================

export async function listAssistantConversations(
  projectName: string,
  mode: 'dev' | 'uat' = 'dev'
): Promise<AssistantConversation[]> {
  return fetchJSON(`/assistant/conversations/${encodeURIComponent(projectName)}?mode=${mode}`)
}

export async function getAssistantConversation(
  projectName: string,
  conversationId: number,
  mode: 'dev' | 'uat' = 'dev'
): Promise<AssistantConversationDetail> {
  return fetchJSON(
    `/assistant/conversations/${encodeURIComponent(projectName)}/${conversationId}?mode=${mode}`
  )
}

export async function createAssistantConversation(
  projectName: string,
  mode: 'dev' | 'uat' = 'dev'
): Promise<AssistantConversation> {
  return fetchJSON(`/assistant/conversations/${encodeURIComponent(projectName)}?mode=${mode}`, {
    method: 'POST',
  })
}

export async function deleteAssistantConversation(
  projectName: string,
  conversationId: number,
  mode: 'dev' | 'uat' = 'dev'
): Promise<void> {
  await fetchJSON(
    `/assistant/conversations/${encodeURIComponent(projectName)}/${conversationId}?mode=${mode}`,
    { method: 'DELETE' }
  )
}

// ============================================================================
// Settings API
// ============================================================================

export async function getAvailableModels(): Promise<ModelsResponse> {
  return fetchJSON('/settings/models')
}

export async function getSettings(): Promise<Settings> {
  return fetchJSON('/settings')
}

export async function updateSettings(settings: SettingsUpdate): Promise<Settings> {
  return fetchJSON('/settings', {
    method: 'PATCH',
    body: JSON.stringify(settings),
  })
}

// ============================================================================
// Dev Server API
// ============================================================================

export async function getDevServerStatus(projectName: string): Promise<DevServerStatusResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/devserver/status`)
}

export async function startDevServer(
  projectName: string,
  command?: string
): Promise<{ success: boolean; message: string }> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/devserver/start`, {
    method: 'POST',
    body: JSON.stringify({ command }),
  })
}

export async function stopDevServer(
  projectName: string
): Promise<{ success: boolean; message: string }> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/devserver/stop`, {
    method: 'POST',
  })
}

export async function getDevServerConfig(projectName: string): Promise<DevServerConfig> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/devserver/config`)
}

// ============================================================================
// Terminal API
// ============================================================================

export async function listTerminals(projectName: string): Promise<TerminalInfo[]> {
  return fetchJSON(`/terminal/${encodeURIComponent(projectName)}`)
}

export async function createTerminal(
  projectName: string,
  name?: string
): Promise<TerminalInfo> {
  return fetchJSON(`/terminal/${encodeURIComponent(projectName)}`, {
    method: 'POST',
    body: JSON.stringify({ name: name ?? null }),
  })
}

export async function renameTerminal(
  projectName: string,
  terminalId: string,
  name: string
): Promise<TerminalInfo> {
  return fetchJSON(`/terminal/${encodeURIComponent(projectName)}/${terminalId}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })
}

export async function deleteTerminal(
  projectName: string,
  terminalId: string
): Promise<void> {
  await fetchJSON(`/terminal/${encodeURIComponent(projectName)}/${terminalId}`, {
    method: 'DELETE',
  })
}

// ============================================================================
// Schedule API
// ============================================================================

export async function listSchedules(projectName: string): Promise<ScheduleListResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/schedules`)
}

export async function createSchedule(
  projectName: string,
  schedule: ScheduleCreate
): Promise<Schedule> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/schedules`, {
    method: 'POST',
    body: JSON.stringify(schedule),
  })
}

export async function getSchedule(
  projectName: string,
  scheduleId: number
): Promise<Schedule> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/schedules/${scheduleId}`)
}

export async function updateSchedule(
  projectName: string,
  scheduleId: number,
  update: ScheduleUpdate
): Promise<Schedule> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/schedules/${scheduleId}`, {
    method: 'PATCH',
    body: JSON.stringify(update),
  })
}

export async function deleteSchedule(
  projectName: string,
  scheduleId: number
): Promise<void> {
  await fetchJSON(`/projects/${encodeURIComponent(projectName)}/schedules/${scheduleId}`, {
    method: 'DELETE',
  })
}

export async function getNextScheduledRun(projectName: string): Promise<NextRunResponse> {
  return fetchJSON(`/projects/${encodeURIComponent(projectName)}/schedules/next`)
}

// ============================================================================
// UAT Tests API (queries uat_tests.db instead of features.db)
// ============================================================================

export async function listUATTests(project?: string): Promise<FeatureListResponse> {
  const url = project ? `/uat/tests?project=${encodeURIComponent(project)}` : '/uat/tests'
  return fetchJSON(url)
}

export async function getUATTest(testId: number): Promise<Feature> {
  return fetchJSON(`/uat/tests/${testId}`)
}

export async function getUATStatsSummary(): Promise<{
  total: number
  passing: number
  in_progress: number
  percentage: number
}> {
  return fetchJSON('/uat/stats/summary')
}

export async function createUATTest(testData: {
  scenario: string
  journey: string
  phase: 'smoke' | 'functional' | 'regression' | 'uat'
  steps: string[]
  expected_result: string
  category?: string
  priority?: number
}): Promise<{
  success: boolean
  test_id: number
  message: string
  test: Feature
}> {
  const response = await fetch('/api/uat/tests', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(testData),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to create UAT test')
  }

  return response.json()
}

// ============================================================================
// Blocker Management API
// ============================================================================

export async function detectBlockers(projectName: string, projectPath: string): Promise<{
  blockers_detected: boolean
  blockers: Array<{
    id: string
    blocker_type: string
    service: string
    key_name?: string
    description: string
    affected_tests: string[]
    suggested_actions: string[]
    priority: string
  }>
  summary: string
}> {
  const response = await fetch('/api/blocker/detect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_name: projectName, project_path: projectPath })
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to detect blockers')
  }

  return response.json()
}

export async function respondToBlocker(request: {
  blocker_id: string
  action: string
  value?: string
  project_name: string
}): Promise<{
  blocker_id: string
  status: string
  message: string
}> {
  const response = await fetch('/api/blocker/respond', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to resolve blocker')
  }

  return response.json()
}

export async function testConnection(request: {
  blocker_id: string
  blocker_type: string
  service: string
  test_params?: Record<string, any>
  timeout?: number
}): Promise<{
  blocker_id: string
  success: boolean
  message: string
  details?: Record<string, any>
}> {
  const response = await fetch('/api/blocker/test-connection', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to test connection')
  }

  return response.json()
}

export async function getPendingBlockers(projectName: string): Promise<{
  project_name: string
  pending_blockers: any[]
  resolved_count: number
  total_count: number
}> {
  return fetchJSON(`/blocker/pending/${projectName}`)
}

export async function getUATProjectContext(
  projectName: string
): Promise<{
  success: boolean
  project_name: string
  has_spec: boolean
  spec_content: string | null
  completed_features_count: number
  completed_features: Array<{
    id: number
    priority: number
    category: string
    name: string
    description: string
    completed_at: string | null
  }>
  uat_cycles_count: number
  uat_cycles: Array<{
    id: number
    name: string
    phase: string
    journey: string
    status: string
    result: string
  }>
  message: string
}> {
  return fetchJSON(`/uat/context/${encodeURIComponent(projectName)}`)
}

export async function triggerUATExecution(
  projectName: string
): Promise<{
  success: boolean
  message: string
  cycle_id: string
  agents_spawned?: number
  tests_assigned?: number
  execution_mode?: string
}> {
  return fetchJSON('/uat/trigger', {
    method: 'POST',
    body: JSON.stringify({
      project_name: projectName
    }),
  })
}

export async function getUATProgress(cycleId: string): Promise<{
  cycle_id: string
  total_tests: number
  passed: number
  failed: number
  running: number
  pending: number
  active_agents: number
  started_at: string | null
  updated_at: string
  tests?: Array<{
    id: number
    scenario: string
    phase: string
    journey: string
    test_type: string
    status: string
    duration?: number
    devlayer_card_id?: number
    error?: string
  }>
}> {
  return fetchJSON(`/uat/progress/${encodeURIComponent(cycleId)}`)
}
