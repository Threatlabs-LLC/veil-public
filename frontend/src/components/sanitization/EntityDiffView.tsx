import type { SanitizationEvent } from '../../api/client'

const TYPE_BG: Record<string, string> = {
  IP_ADDRESS: 'bg-red-800/40 border-red-600/50',
  EMAIL: 'bg-blue-800/40 border-blue-600/50',
  CREDIT_CARD: 'bg-amber-800/40 border-amber-600/50',
  SSN: 'bg-purple-800/40 border-purple-600/50',
  PHONE: 'bg-green-800/40 border-green-600/50',
  URL: 'bg-cyan-800/40 border-cyan-600/50',
  HOSTNAME: 'bg-orange-800/40 border-orange-600/50',
  PERSON: 'bg-pink-800/40 border-pink-600/50',
  ORGANIZATION: 'bg-violet-800/40 border-violet-600/50',
  COMPANY_NAME: 'bg-violet-800/40 border-violet-600/50',
  API_KEY: 'bg-yellow-800/40 border-yellow-600/50',
  SECRET: 'bg-yellow-800/40 border-yellow-600/50',
  MAC_ADDRESS: 'bg-indigo-800/40 border-indigo-600/50',
  CONNECTION_STRING: 'bg-rose-800/40 border-rose-600/50',
  AWS_KEY: 'bg-yellow-800/40 border-yellow-600/50',
  DATE_OF_BIRTH: 'bg-teal-800/40 border-teal-600/50',
  ADDRESS: 'bg-emerald-800/40 border-emerald-600/50',
  AUTH_TOKEN: 'bg-red-800/40 border-red-600/50',
  PRIVATE_KEY: 'bg-red-800/40 border-red-600/50',
  CREDENTIAL: 'bg-red-800/40 border-red-600/50',
  FILE_PATH: 'bg-slate-800/40 border-slate-600/50',
  USERNAME: 'bg-fuchsia-800/40 border-fuchsia-600/50',
  WINDOWS_SID: 'bg-zinc-800/40 border-zinc-600/50',
  LDAP_DN: 'bg-lime-800/40 border-lime-600/50',
  DEVICE_ID: 'bg-orange-800/40 border-orange-600/50',
  HASH: 'bg-gray-800/40 border-gray-600/50',
  COMMAND_LINE: 'bg-rose-800/40 border-rose-600/50',
}

const DEFAULT_BG = 'bg-gray-700/40 border-gray-500/50'

interface Props {
  sanitization: SanitizationEvent
}

interface TextSegment {
  text: string
  isEntity: boolean
  entityType?: string
  placeholder?: string
}

function buildSegments(sanitization: SanitizationEvent): TextSegment[] {
  const { original_text, entities } = sanitization
  if (!entities.length) return [{ text: original_text, isEntity: false }]

  // Sort entities by start position
  const sorted = [...entities].sort((a, b) => a.start - b.start)

  const segments: TextSegment[] = []
  let lastEnd = 0

  for (const entity of sorted) {
    // Text before this entity
    if (entity.start > lastEnd) {
      segments.push({ text: original_text.slice(lastEnd, entity.start), isEntity: false })
    }
    // The entity itself
    segments.push({
      text: entity.original,
      isEntity: true,
      entityType: entity.entity_type,
      placeholder: entity.placeholder,
    })
    lastEnd = entity.end
  }

  // Remaining text after last entity
  if (lastEnd < original_text.length) {
    segments.push({ text: original_text.slice(lastEnd), isEntity: false })
  }

  return segments
}

export default function EntityDiffView({ sanitization }: Props) {
  const segments = buildSegments(sanitization)

  if (!sanitization.entities.length) {
    return (
      <div className="text-xs text-gray-400 italic">
        No sensitive data detected in this message.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Original with highlights */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5 font-medium">
          Original (highlighted)
        </div>
        <div className="text-xs bg-gray-800/50 rounded-lg p-2.5 leading-relaxed whitespace-pre-wrap break-words">
          {segments.map((seg, i) =>
            seg.isEntity ? (
              <span
                key={i}
                className={`inline-block border rounded px-0.5 mx-0.5 ${TYPE_BG[seg.entityType!] ?? DEFAULT_BG}`}
                title={`${seg.entityType} → ${seg.placeholder}`}
              >
                <span className="font-mono">{seg.text}</span>
                <sup className="text-[8px] ml-0.5 opacity-60">{seg.placeholder}</sup>
              </span>
            ) : (
              <span key={i} className="text-gray-300">{seg.text}</span>
            )
          )}
        </div>
      </div>

      {/* Sanitized version */}
      <div>
        <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5 font-medium">
          Sent to LLM
        </div>
        <pre className="text-xs bg-gray-800/50 rounded-lg p-2.5 whitespace-pre-wrap break-words text-gray-300 font-mono">
          {sanitization.sanitized_text}
        </pre>
      </div>
    </div>
  )
}
