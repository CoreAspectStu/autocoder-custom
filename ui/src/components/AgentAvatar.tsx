import { type AgentMascot, type AgentState } from '../lib/types'

interface AgentAvatarProps {
  name: AgentMascot
  state: AgentState
  size?: 'sm' | 'md' | 'lg'
  showName?: boolean
}

const AVATAR_COLORS: Record<AgentMascot, { primary: string; secondary: string; accent: string }> = {
  Spark: { primary: '#3B82F6', secondary: '#60A5FA', accent: '#DBEAFE' },  // Blue robot
  Fizz: { primary: '#F97316', secondary: '#FB923C', accent: '#FFEDD5' },   // Orange fox
  Octo: { primary: '#8B5CF6', secondary: '#A78BFA', accent: '#EDE9FE' },   // Purple octopus
  Hoot: { primary: '#22C55E', secondary: '#4ADE80', accent: '#DCFCE7' },   // Green owl
  Buzz: { primary: '#EAB308', secondary: '#FACC15', accent: '#FEF9C3' },   // Yellow bee
}

const SIZES = {
  sm: { svg: 32, font: 'text-xs' },
  md: { svg: 48, font: 'text-sm' },
  lg: { svg: 64, font: 'text-base' },
}

// SVG mascot definitions - simple cute characters
function SparkSVG({ colors, size }: { colors: typeof AVATAR_COLORS.Spark; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      {/* Robot body */}
      <rect x="16" y="20" width="32" height="28" rx="4" fill={colors.primary} />
      {/* Robot head */}
      <rect x="12" y="8" width="40" height="24" rx="4" fill={colors.secondary} />
      {/* Antenna */}
      <circle cx="32" cy="4" r="4" fill={colors.primary} className="animate-pulse" />
      <rect x="30" y="4" width="4" height="8" fill={colors.primary} />
      {/* Eyes */}
      <circle cx="24" cy="18" r="4" fill="white" />
      <circle cx="40" cy="18" r="4" fill="white" />
      <circle cx="25" cy="18" r="2" fill={colors.primary} />
      <circle cx="41" cy="18" r="2" fill={colors.primary} />
      {/* Mouth */}
      <rect x="26" y="24" width="12" height="2" rx="1" fill="white" />
      {/* Arms */}
      <rect x="6" y="24" width="8" height="4" rx="2" fill={colors.primary} />
      <rect x="50" y="24" width="8" height="4" rx="2" fill={colors.primary} />
    </svg>
  )
}

function FizzSVG({ colors, size }: { colors: typeof AVATAR_COLORS.Fizz; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      {/* Ears */}
      <polygon points="12,12 20,28 4,28" fill={colors.primary} />
      <polygon points="52,12 60,28 44,28" fill={colors.primary} />
      <polygon points="14,14 18,26 8,26" fill={colors.accent} />
      <polygon points="50,14 56,26 44,26" fill={colors.accent} />
      {/* Head */}
      <ellipse cx="32" cy="36" rx="24" ry="22" fill={colors.primary} />
      {/* Face */}
      <ellipse cx="32" cy="40" rx="18" ry="14" fill={colors.accent} />
      {/* Eyes */}
      <ellipse cx="24" cy="32" rx="4" ry="5" fill="white" />
      <ellipse cx="40" cy="32" rx="4" ry="5" fill="white" />
      <circle cx="25" cy="33" r="2" fill="#1a1a1a" />
      <circle cx="41" cy="33" r="2" fill="#1a1a1a" />
      {/* Nose */}
      <ellipse cx="32" cy="42" rx="4" ry="3" fill={colors.primary} />
      {/* Whiskers */}
      <line x1="8" y1="38" x2="18" y2="40" stroke={colors.primary} strokeWidth="2" />
      <line x1="8" y1="44" x2="18" y2="44" stroke={colors.primary} strokeWidth="2" />
      <line x1="46" y1="40" x2="56" y2="38" stroke={colors.primary} strokeWidth="2" />
      <line x1="46" y1="44" x2="56" y2="44" stroke={colors.primary} strokeWidth="2" />
    </svg>
  )
}

function OctoSVG({ colors, size }: { colors: typeof AVATAR_COLORS.Octo; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      {/* Tentacles */}
      <path d="M12,48 Q8,56 12,60 Q16,64 20,58" fill={colors.secondary} />
      <path d="M22,50 Q20,58 24,62" fill={colors.secondary} />
      <path d="M32,52 Q32,60 36,62" fill={colors.secondary} />
      <path d="M42,50 Q44,58 40,62" fill={colors.secondary} />
      <path d="M52,48 Q56,56 52,60 Q48,64 44,58" fill={colors.secondary} />
      {/* Head */}
      <ellipse cx="32" cy="32" rx="22" ry="24" fill={colors.primary} />
      {/* Eyes */}
      <ellipse cx="24" cy="28" rx="6" ry="8" fill="white" />
      <ellipse cx="40" cy="28" rx="6" ry="8" fill="white" />
      <ellipse cx="25" cy="30" rx="3" ry="4" fill={colors.primary} />
      <ellipse cx="41" cy="30" rx="3" ry="4" fill={colors.primary} />
      {/* Smile */}
      <path d="M24,42 Q32,48 40,42" stroke={colors.accent} strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  )
}

function HootSVG({ colors, size }: { colors: typeof AVATAR_COLORS.Hoot; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      {/* Ear tufts */}
      <polygon points="14,8 22,24 6,20" fill={colors.primary} />
      <polygon points="50,8 58,20 42,24" fill={colors.primary} />
      {/* Body */}
      <ellipse cx="32" cy="40" rx="20" ry="18" fill={colors.primary} />
      {/* Head */}
      <circle cx="32" cy="28" r="20" fill={colors.secondary} />
      {/* Eye circles */}
      <circle cx="24" cy="26" r="10" fill={colors.accent} />
      <circle cx="40" cy="26" r="10" fill={colors.accent} />
      {/* Eyes */}
      <circle cx="24" cy="26" r="6" fill="white" />
      <circle cx="40" cy="26" r="6" fill="white" />
      <circle cx="25" cy="27" r="3" fill="#1a1a1a" />
      <circle cx="41" cy="27" r="3" fill="#1a1a1a" />
      {/* Beak */}
      <polygon points="32,32 28,40 36,40" fill="#F97316" />
      {/* Belly */}
      <ellipse cx="32" cy="46" rx="10" ry="8" fill={colors.accent} />
    </svg>
  )
}

function BuzzSVG({ colors, size }: { colors: typeof AVATAR_COLORS.Buzz; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      {/* Wings */}
      <ellipse cx="14" cy="32" rx="10" ry="14" fill={colors.accent} opacity="0.8" className="animate-pulse" />
      <ellipse cx="50" cy="32" rx="10" ry="14" fill={colors.accent} opacity="0.8" className="animate-pulse" />
      {/* Body stripes */}
      <ellipse cx="32" cy="36" rx="14" ry="20" fill={colors.primary} />
      <ellipse cx="32" cy="30" rx="12" ry="6" fill="#1a1a1a" />
      <ellipse cx="32" cy="44" rx="12" ry="6" fill="#1a1a1a" />
      {/* Head */}
      <circle cx="32" cy="16" r="12" fill={colors.primary} />
      {/* Antennae */}
      <line x1="26" y1="8" x2="22" y2="2" stroke="#1a1a1a" strokeWidth="2" />
      <line x1="38" y1="8" x2="42" y2="2" stroke="#1a1a1a" strokeWidth="2" />
      <circle cx="22" cy="2" r="2" fill="#1a1a1a" />
      <circle cx="42" cy="2" r="2" fill="#1a1a1a" />
      {/* Eyes */}
      <circle cx="28" cy="14" r="4" fill="white" />
      <circle cx="36" cy="14" r="4" fill="white" />
      <circle cx="29" cy="15" r="2" fill="#1a1a1a" />
      <circle cx="37" cy="15" r="2" fill="#1a1a1a" />
      {/* Smile */}
      <path d="M28,20 Q32,24 36,20" stroke="#1a1a1a" strokeWidth="1.5" fill="none" strokeLinecap="round" />
    </svg>
  )
}

const MASCOT_SVGS: Record<AgentMascot, typeof SparkSVG> = {
  Spark: SparkSVG,
  Fizz: FizzSVG,
  Octo: OctoSVG,
  Hoot: HootSVG,
  Buzz: BuzzSVG,
}

// Animation classes based on state
function getStateAnimation(state: AgentState): string {
  switch (state) {
    case 'idle':
      return 'animate-bounce-gentle'
    case 'thinking':
      return 'animate-thinking'
    case 'working':
      return 'animate-working'
    case 'testing':
      return 'animate-testing'
    case 'success':
      return 'animate-celebrate'
    case 'error':
    case 'struggling':
      return 'animate-shake-gentle'
    default:
      return ''
  }
}

// Glow effect based on state
function getStateGlow(state: AgentState): string {
  switch (state) {
    case 'working':
      return 'shadow-[0_0_12px_rgba(0,180,216,0.5)]'
    case 'thinking':
      return 'shadow-[0_0_8px_rgba(255,214,10,0.4)]'
    case 'success':
      return 'shadow-[0_0_16px_rgba(112,224,0,0.6)]'
    case 'error':
    case 'struggling':
      return 'shadow-[0_0_12px_rgba(255,84,0,0.5)]'
    default:
      return ''
  }
}

// Get human-readable state description for accessibility
function getStateDescription(state: AgentState): string {
  switch (state) {
    case 'idle':
      return 'waiting'
    case 'thinking':
      return 'analyzing'
    case 'working':
      return 'coding'
    case 'testing':
      return 'running tests'
    case 'success':
      return 'completed successfully'
    case 'error':
      return 'encountered an error'
    case 'struggling':
      return 'having difficulty'
    default:
      return state
  }
}

export function AgentAvatar({ name, state, size = 'md', showName = false }: AgentAvatarProps) {
  const colors = AVATAR_COLORS[name]
  const { svg: svgSize, font } = SIZES[size]
  const SvgComponent = MASCOT_SVGS[name]
  const stateDesc = getStateDescription(state)
  const ariaLabel = `Agent ${name} is ${stateDesc}`

  return (
    <div
      className="flex flex-col items-center gap-1"
      role="status"
      aria-label={ariaLabel}
      aria-live="polite"
    >
      <div
        className={`
          rounded-full p-1 transition-all duration-300
          ${getStateAnimation(state)}
          ${getStateGlow(state)}
        `}
        style={{ backgroundColor: colors.accent }}
        title={ariaLabel}
        role="img"
        aria-hidden="true"
      >
        <SvgComponent colors={colors} size={svgSize} />
      </div>
      {showName && (
        <span className={`${font} font-bold text-neo-text`} style={{ color: colors.primary }}>
          {name}
        </span>
      )}
    </div>
  )
}

// Get mascot name by index (cycles through available mascots)
export function getMascotName(index: number): AgentMascot {
  const mascots: AgentMascot[] = ['Spark', 'Fizz', 'Octo', 'Hoot', 'Buzz']
  return mascots[index % mascots.length]
}
