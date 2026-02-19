import { useState, useCallback, useRef } from 'react'
import { FileUp, FileText, Shield, Upload, X, AlertTriangle, CheckCircle } from 'lucide-react'
import { api } from '../api/client'

const ACCEPTED_TYPES = '.pdf,.docx,.txt,.csv,.xlsx'
const MAX_FILE_SIZE_MB = 10

interface ScanResult {
  document_id: string
  filename: string
  file_type: string
  file_size_bytes: number
  char_count: number
  page_count: number | null
  was_truncated: boolean
  sanitized_text: string
  entity_count: number
  entities: Array<{
    entity_type: string
    placeholder: string
    original: string
    confidence: number
    start: number
    end: number
    detection_method: string
  }>
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const ENTITY_COLORS: Record<string, string> = {
  EMAIL: 'bg-blue-900/40 text-blue-300 border-blue-700/50',
  CREDIT_CARD: 'bg-red-900/40 text-red-300 border-red-700/50',
  SSN: 'bg-red-900/40 text-red-300 border-red-700/50',
  PHONE: 'bg-green-900/40 text-green-300 border-green-700/50',
  IP_ADDRESS: 'bg-yellow-900/40 text-yellow-300 border-yellow-700/50',
  URL: 'bg-cyan-900/40 text-cyan-300 border-cyan-700/50',
  HOSTNAME: 'bg-cyan-900/40 text-cyan-300 border-cyan-700/50',
  PERSON: 'bg-purple-900/40 text-purple-300 border-purple-700/50',
  ORGANIZATION: 'bg-purple-900/40 text-purple-300 border-purple-700/50',
  SECRET: 'bg-orange-900/40 text-orange-300 border-orange-700/50',
  API_KEY: 'bg-orange-900/40 text-orange-300 border-orange-700/50',
  AUTH_TOKEN: 'bg-orange-900/40 text-orange-300 border-orange-700/50',
  CONNECTION_STRING: 'bg-orange-900/40 text-orange-300 border-orange-700/50',
  USERNAME: 'bg-indigo-900/40 text-indigo-300 border-indigo-700/50',
}

function getEntityColor(type: string) {
  return ENTITY_COLORS[type] || 'bg-gray-800 text-gray-300 border-gray-700/50'
}

export default function Documents() {
  const [isDragging, setIsDragging] = useState(false)
  const [isScanning, setIsScanning] = useState(false)
  const [result, setResult] = useState<ScanResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const scanFile = useCallback(async (file: File) => {
    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setError(`File exceeds ${MAX_FILE_SIZE_MB} MB limit`)
      return
    }

    setSelectedFile(file)
    setIsScanning(true)
    setError(null)
    setResult(null)

    try {
      const data = await api.scanDocument(file)
      setResult(data)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setIsScanning(false)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) scanFile(file)
  }, [scanFile])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleFileSelect = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) scanFile(file)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [scanFile])

  const reset = useCallback(() => {
    setResult(null)
    setError(null)
    setSelectedFile(null)
  }, [])

  // Group entities by type for the summary
  const entityGroups = result?.entities.reduce((acc, e) => {
    acc[e.entity_type] = (acc[e.entity_type] || 0) + 1
    return acc
  }, {} as Record<string, number>) ?? {}

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex-1 flex flex-col">
        <header className="h-14 border-b border-gray-800 flex items-center px-4 gap-2">
          <FileText className="w-5 h-5 text-veil-500" />
          <span className="font-medium">Document Scanner</span>
        </header>

        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto py-6 px-4">
            {/* Upload area */}
            {!result && !isScanning && (
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                className={`border-2 border-dashed rounded-2xl p-12 text-center transition-colors ${
                  isDragging
                    ? 'border-veil-500 bg-veil-900/20'
                    : 'border-gray-700 hover:border-gray-600'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPTED_TYPES}
                  onChange={handleFileChange}
                  className="hidden"
                />
                <Upload className={`w-12 h-12 mx-auto mb-4 ${isDragging ? 'text-veil-400' : 'text-gray-600'}`} />
                <h2 className="text-lg font-medium mb-2">
                  {isDragging ? 'Drop your file here' : 'Scan a document for sensitive data'}
                </h2>
                <p className="text-sm text-gray-400 mb-6">
                  Drag and drop a file, or click to browse. Supported: PDF, DOCX, TXT, CSV, XLSX (max {MAX_FILE_SIZE_MB} MB)
                </p>
                <button
                  onClick={handleFileSelect}
                  className="px-6 py-2.5 bg-veil-600 hover:bg-veil-700 rounded-lg transition-colors text-sm font-medium inline-flex items-center gap-2"
                >
                  <FileUp className="w-4 h-4" />
                  Choose File
                </button>
              </div>
            )}

            {/* Scanning state */}
            {isScanning && (
              <div className="border border-gray-800 rounded-2xl p-12 text-center">
                <div className="w-12 h-12 mx-auto mb-4 border-2 border-veil-500 border-t-transparent rounded-full animate-spin" />
                <h2 className="text-lg font-medium mb-1">Scanning document...</h2>
                <p className="text-sm text-gray-400">
                  Extracting text and detecting sensitive data in {selectedFile?.name}
                </p>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 mb-4 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-red-300">Scan failed</p>
                  <p className="text-sm text-red-400/80 mt-0.5">{error}</p>
                </div>
                <button onClick={reset} className="ml-auto text-red-400 hover:text-red-300">
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Results */}
            {result && (
              <div className="space-y-4">
                {/* Summary header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${result.entity_count > 0 ? 'bg-amber-900/30' : 'bg-green-900/30'}`}>
                      {result.entity_count > 0
                        ? <AlertTriangle className="w-5 h-5 text-amber-400" />
                        : <CheckCircle className="w-5 h-5 text-green-400" />
                      }
                    </div>
                    <div>
                      <h2 className="font-medium">
                        {result.entity_count > 0
                          ? `${result.entity_count} sensitive ${result.entity_count === 1 ? 'item' : 'items'} detected`
                          : 'No sensitive data detected'
                        }
                      </h2>
                      <p className="text-xs text-gray-400">
                        {result.filename} ({formatFileSize(result.file_size_bytes)})
                        {result.page_count != null && ` \u00b7 ${result.page_count} page${result.page_count !== 1 ? 's' : ''}`}
                        {` \u00b7 ${result.char_count.toLocaleString()} chars`}
                        {result.was_truncated && ' (truncated)'}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={reset}
                    className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors text-sm"
                  >
                    Scan Another
                  </button>
                </div>

                {/* Entity type breakdown */}
                {result.entity_count > 0 && (
                  <div className="bg-gray-800/40 border border-gray-800 rounded-xl p-4">
                    <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
                      <Shield className="w-4 h-4 text-veil-400" />
                      Detection Summary
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(entityGroups)
                        .sort(([, a], [, b]) => b - a)
                        .map(([type, count]) => (
                          <span
                            key={type}
                            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border ${getEntityColor(type)}`}
                          >
                            <span className="font-medium">{type}</span>
                            <span className="opacity-70">{count}</span>
                          </span>
                        ))
                      }
                    </div>
                  </div>
                )}

                {/* Entity detail table */}
                {result.entities.length > 0 && (
                  <div className="bg-gray-800/40 border border-gray-800 rounded-xl overflow-hidden">
                    <div className="px-4 py-3 border-b border-gray-800">
                      <h3 className="text-sm font-medium">Detected Entities</h3>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-800 text-left text-xs text-gray-400">
                            <th className="px-4 py-2 font-medium">Type</th>
                            <th className="px-4 py-2 font-medium">Original Value</th>
                            <th className="px-4 py-2 font-medium">Placeholder</th>
                            <th className="px-4 py-2 font-medium">Confidence</th>
                            <th className="px-4 py-2 font-medium">Method</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.entities.map((entity, i) => (
                            <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                              <td className="px-4 py-2">
                                <span className={`inline-block px-2 py-0.5 rounded text-xs border ${getEntityColor(entity.entity_type)}`}>
                                  {entity.entity_type}
                                </span>
                              </td>
                              <td className="px-4 py-2 font-mono text-xs text-red-300 max-w-xs truncate">
                                {entity.original}
                              </td>
                              <td className="px-4 py-2 font-mono text-xs text-veil-300">
                                {entity.placeholder}
                              </td>
                              <td className="px-4 py-2 text-xs">
                                <span className={entity.confidence >= 0.9 ? 'text-green-400' : entity.confidence >= 0.7 ? 'text-yellow-400' : 'text-gray-400'}>
                                  {(entity.confidence * 100).toFixed(0)}%
                                </span>
                              </td>
                              <td className="px-4 py-2 text-xs text-gray-400">{entity.detection_method}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Sanitized text preview */}
                <div className="bg-gray-800/40 border border-gray-800 rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
                    <h3 className="text-sm font-medium">Sanitized Text Preview</h3>
                    <span className="text-xs text-gray-500">
                      {result.entity_count > 0 ? 'Sensitive values replaced with placeholders' : 'No changes needed'}
                    </span>
                  </div>
                  <pre className="p-4 text-xs text-gray-300 whitespace-pre-wrap break-words max-h-96 overflow-y-auto font-mono leading-relaxed">
                    {result.sanitized_text || '(empty document)'}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
