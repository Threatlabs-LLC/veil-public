import clsx from 'clsx'

interface Props {
  entityType: string
  original: string
  placeholder: string
  confidence: number
  showOriginal: boolean
}

const TYPE_COLORS: Record<string, string> = {
  IP_ADDRESS: 'bg-red-900/50 text-red-300 border-red-700',
  EMAIL: 'bg-blue-900/50 text-blue-300 border-blue-700',
  CREDIT_CARD: 'bg-amber-900/50 text-amber-300 border-amber-700',
  SSN: 'bg-purple-900/50 text-purple-300 border-purple-700',
  PHONE: 'bg-green-900/50 text-green-300 border-green-700',
  URL: 'bg-cyan-900/50 text-cyan-300 border-cyan-700',
  HOSTNAME: 'bg-orange-900/50 text-orange-300 border-orange-700',
  PERSON: 'bg-pink-900/50 text-pink-300 border-pink-700',
  ORGANIZATION: 'bg-violet-900/50 text-violet-300 border-violet-700',
  COMPANY_NAME: 'bg-violet-900/50 text-violet-300 border-violet-700',
  API_KEY: 'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  SECRET: 'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  MAC_ADDRESS: 'bg-indigo-900/50 text-indigo-300 border-indigo-700',
  CONNECTION_STRING: 'bg-rose-900/50 text-rose-300 border-rose-700',
  AWS_KEY: 'bg-yellow-900/50 text-yellow-300 border-yellow-700',
  DATE_OF_BIRTH: 'bg-teal-900/50 text-teal-300 border-teal-700',
  ADDRESS: 'bg-emerald-900/50 text-emerald-300 border-emerald-700',
  AUTH_TOKEN: 'bg-red-900/50 text-red-300 border-red-700',
  PRIVATE_KEY: 'bg-red-900/50 text-red-300 border-red-700',
  CREDENTIAL: 'bg-red-900/50 text-red-300 border-red-700',
  FILE_PATH: 'bg-slate-900/50 text-slate-300 border-slate-700',
  USERNAME: 'bg-fuchsia-900/50 text-fuchsia-300 border-fuchsia-700',
  WINDOWS_SID: 'bg-zinc-900/50 text-zinc-300 border-zinc-700',
  LDAP_DN: 'bg-lime-900/50 text-lime-300 border-lime-700',
  DEVICE_ID: 'bg-orange-900/50 text-orange-300 border-orange-700',
  HASH: 'bg-gray-900/50 text-gray-300 border-gray-700',
  COMMAND_LINE: 'bg-rose-900/50 text-rose-300 border-rose-700',
}

const DEFAULT_COLOR = 'bg-gray-800 text-gray-300 border-gray-600'

export default function EntityBadge({ entityType, original, placeholder, confidence, showOriginal }: Props) {
  const colorClass = TYPE_COLORS[entityType] ?? DEFAULT_COLOR

  return (
    <div className={clsx('rounded-lg border p-2 text-xs', colorClass)}>
      <div className="flex items-center justify-between mb-1">
        <span className="font-mono font-medium">{placeholder}</span>
        <span className="opacity-60">{Math.round(confidence * 100)}%</span>
      </div>
      <div className="font-mono text-[11px] opacity-80">
        {showOriginal ? original : original.replace(/./g, '\u2022')}
      </div>
      <div className="mt-1 opacity-50 text-[10px] uppercase tracking-wider">
        {entityType.replace(/_/g, ' ')}
      </div>
    </div>
  )
}
