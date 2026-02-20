import { Home } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <div className="text-6xl font-bold text-gray-700 mb-2">404</div>
        <h1 className="text-xl font-semibold mb-2">Page not found</h1>
        <p className="text-gray-400 mb-6">The page you're looking for doesn't exist or has been moved.</p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-veil-600 hover:bg-veil-700 rounded-lg text-sm font-medium transition-colors"
        >
          <Home className="w-4 h-4" />
          Go home
        </Link>
      </div>
    </div>
  )
}
