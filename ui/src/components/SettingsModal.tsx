import { Loader2, AlertCircle } from 'lucide-react'
import { useSettings, useUpdateSettings, useAvailableModels } from '../hooks/useProjects'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

interface SettingsModalProps {
  isOpen: boolean
  onClose: () => void
}

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { data: settings, isLoading, isError, refetch } = useSettings()
  const { data: modelsData } = useAvailableModels()
  const updateSettings = useUpdateSettings()

  const handleYoloToggle = () => {
    if (settings && !updateSettings.isPending) {
      updateSettings.mutate({ yolo_mode: !settings.yolo_mode })
    }
  }

  const handleModelChange = (modelId: string) => {
    if (!updateSettings.isPending) {
      updateSettings.mutate({ model: modelId })
    }
  }

  const handleTestingRatioChange = (ratio: number) => {
    if (!updateSettings.isPending) {
      updateSettings.mutate({ testing_agent_ratio: ratio })
    }
  }

  const models = modelsData?.models ?? []
  const isSaving = updateSettings.isPending

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Settings
            {isSaving && <Loader2 className="animate-spin" size={16} />}
          </DialogTitle>
        </DialogHeader>

        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="animate-spin" size={24} />
            <span className="ml-2">Loading settings...</span>
          </div>
        )}

        {/* Error State */}
        {isError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              Failed to load settings
              <Button
                variant="link"
                onClick={() => refetch()}
                className="ml-2 p-0 h-auto"
              >
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {/* Settings Content */}
        {settings && !isLoading && (
          <div className="space-y-6">
            {/* YOLO Mode Toggle */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="yolo-mode" className="font-medium">
                  YOLO Mode
                </Label>
                <p className="text-sm text-muted-foreground">
                  Skip testing for rapid prototyping
                </p>
              </div>
              <Switch
                id="yolo-mode"
                checked={settings.yolo_mode}
                onCheckedChange={handleYoloToggle}
                disabled={isSaving}
              />
            </div>

            {/* Model Selection */}
            <div className="space-y-2">
              <Label className="font-medium">Model</Label>
              <div className="flex rounded-lg border overflow-hidden">
                {models.map((model) => (
                  <button
                    key={model.id}
                    onClick={() => handleModelChange(model.id)}
                    disabled={isSaving}
                    className={`flex-1 py-2 px-3 text-sm font-medium transition-colors ${
                      settings.model === model.id
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-background text-foreground hover:bg-muted'
                    } ${isSaving ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    {model.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Regression Agents */}
            <div className="space-y-2">
              <Label className="font-medium">Regression Agents</Label>
              <p className="text-sm text-muted-foreground">
                Number of regression testing agents (0 = disabled)
              </p>
              <div className="flex rounded-lg border overflow-hidden">
                {[0, 1, 2, 3].map((ratio) => (
                  <button
                    key={ratio}
                    onClick={() => handleTestingRatioChange(ratio)}
                    disabled={isSaving}
                    className={`flex-1 py-2 px-3 text-sm font-medium transition-colors ${
                      settings.testing_agent_ratio === ratio
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-background text-foreground hover:bg-muted'
                    } ${isSaving ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    {ratio}
                  </button>
                ))}
              </div>
            </div>

            {/* Update Error */}
            {updateSettings.isError && (
              <Alert variant="destructive">
                <AlertDescription>
                  Failed to save settings. Please try again.
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
