import { ShieldCheck, Eye, EyeOff, ChevronRight, Diff } from 'lucide-react'
import { useState } from 'react'
import type { SanitizationEvent } from '../../api/client'
import EntityBadge from './EntityBadge'
import EntityDiffView from './EntityDiffView'

interface Props {
  sanitization: SanitizationEvent | null
}

type ViewMode = 'badges' | 'diff'

export default function SanitizationPanel({ sanitization }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [showOriginals, setShowOriginals] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('badges')

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="w-10 bg-gray-900 border-l border-gray-800 flex flex-col items-center pt-4 hover:bg-gray-800 transition-colors"
        title="Expand sanitization panel"
      >
        <ChevronRight className="w-4 h-4 text-gray-500 rotate-180" />
        <ShieldCheck className="w-5 h-5 text-veil-500 mt-2" />
      </button>
    )
  }

  return (
    <aside className="w-72 bg-gray-900 border-l border-gray-800 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-3 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-veil-500" />
          <h2 className="text-sm font-semibold">Sanitization</h2>
        </div>
        <div className="flex items-center gap-1">
          {/* View mode toggle */}
          {sanitization && sanitization.entities.length > 0 && (
            <button
              onClick={() => setViewMode(viewMode === 'badges' ? 'diff' : 'badges')}
              className="p-1 rounded hover:bg-gray-800 transition-colors"
              title={viewMode === 'badges' ? 'Show diff view' : 'Show badge view'}
            >
              <Diff className={`w-4 h-4 ${viewMode === 'diff' ? 'text-veil-400' : 'text-gray-400'}`} />
            </button>
          )}
          <button
            onClick={() => setShowOriginals(!showOriginals)}
            className="p-1 rounded hover:bg-gray-800 transition-colors"
            title={showOriginals ? 'Hide originals' : 'Show originals'}
          >
            {showOriginals ? (
              <Eye className="w-4 h-4 text-gray-400" />
            ) : (
              <EyeOff className="w-4 h-4 text-gray-400" />
            )}
          </button>
          <button
            onClick={() => setCollapsed(true)}
            className="p-1 rounded hover:bg-gray-800 transition-colors"
            title="Collapse panel"
          >
            <ChevronRight className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {!sanitization ? (
          <div className="text-center text-gray-500 text-xs mt-8">
            <ShieldCheck className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p>Send a message to see detected entities</p>
          </div>
        ) : (
          <>
            {/* Entity count */}
            <div className="flex items-center gap-2 text-xs">
              <span className={
                sanitization.entities.length > 0
                  ? 'text-amber-400'
                  : 'text-green-400'
              }>
                {sanitization.entities.length > 0
                  ? `${sanitization.entities.length} entities detected`
                  : 'No sensitive data detected'
                }
              </span>
            </div>

            {viewMode === 'diff' && sanitization.entities.length > 0 ? (
              <EntityDiffView sanitization={sanitization} />
            ) : (
              <>
                {/* Entity list */}
                {sanitization.entities.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                      Detected Entities
                    </h3>
                    {sanitization.entities.map((entity, i) => (
                      <EntityBadge
                        key={i}
                        entityType={entity.entity_type}
                        original={entity.original}
                        placeholder={entity.placeholder}
                        confidence={entity.confidence}
                        showOriginal={showOriginals}
                      />
                    ))}
                  </div>
                )}

                {/* Sanitized preview */}
                {sanitization.entities.length > 0 && (
                  <div className="space-y-1">
                    <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                      Sent to LLM
                    </h3>
                    <pre className="text-xs bg-gray-800 rounded-lg p-2 whitespace-pre-wrap break-words text-gray-300">
                      {sanitization.sanitized_text}
                    </pre>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* Footer status */}
      <div className="p-3 border-t border-gray-800 text-xs text-gray-500 flex items-center gap-1">
        <div className="w-2 h-2 rounded-full bg-green-500" />
        Protection active
      </div>
    </aside>
  )
}
