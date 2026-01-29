import { FlaskConical, Code } from 'lucide-react'
import { useUATMode } from '../contexts/UATModeContext'

interface UATModeToggleProps {
  projectName: string | null
  hasFeatures: boolean
}

export function UATModeToggle({ projectName, hasFeatures }: UATModeToggleProps) {
  const { toggleMode, isUATMode } = useUATMode()

  // Don't render if no project selected or no features exist
  if (!projectName || !hasFeatures) {
    return null
  }

  const isUAT = isUATMode

  const handleToggle = () => {
    toggleMode()
  }

  return (
    <div className="flex items-center gap-2">
      {/* Mode badge */}
      <span className="text-xs font-bold uppercase tracking-wide">
        {isUAT ? (
          <span className="text-purple-600 dark:text-purple-400">UAT Mode</span>
        ) : (
          <span className="text-gray-600 dark:text-gray-400">Dev Mode</span>
        )}
      </span>

      {/* Toggle button */}
      <button
        onClick={handleToggle}
        className={`
          neo-btn text-sm py-2 px-3 transition-all duration-300
          ${isUAT
            ? 'bg-purple-500 hover:bg-purple-600 text-white border-purple-600 dark:border-purple-400'
            : 'bg-neo-card hover:bg-neo-bg text-neo-text border-neo-border'
          }
        `}
        title={isUAT ? 'Switch to Dev Mode' : 'Switch to UAT Mode'}
        aria-label={isUAT ? 'Switch to Dev Mode' : 'Switch to UAT Mode'}
      >
        {isUAT ? (
          <FlaskConical size={18} />
        ) : (
          <Code size={18} />
        )}
      </button>
    </div>
  )
}
