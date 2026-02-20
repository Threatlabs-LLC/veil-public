import { useEffect, useState } from 'react'
import { CreditCard, ExternalLink, CheckCircle, AlertTriangle, ArrowUpRight } from 'lucide-react'
import { api } from '../api/client'
import { useToast } from '../components/Toast'

interface SubscriptionInfo {
  tier: string
  subscription_status: string | null
  stripe_customer_id: string | null
  has_subscription: boolean
  billing_email: string | null
}

const TIER_FEATURES: Record<string, string[]> = {
  free: ['3 users', '5 custom rules', '7-day audit retention', 'Community support'],
  solo: ['1 user', '10 custom rules', '1 webhook', '30-day audit retention', 'Cloud hosted', 'Email support'],
  team: ['25 users', '100 custom rules', '5 webhooks', '90-day audit retention', 'Multi-provider', 'SSO'],
  business: ['200 users', '500 custom rules', '20 webhooks', '1-year audit retention', 'HIPAA', 'Data residency'],
}

const TIER_PRICES: Record<string, string> = {
  solo: '$9',
  team: '$29',
  business: '$69',
}

const TIER_NAMES: Record<string, string> = {
  free: 'Free',
  solo: 'Solo',
  team: 'Team',
  business: 'Business',
  enterprise: 'Enterprise',
}

export default function Billing() {
  const { toast } = useToast()
  const [sub, setSub] = useState<SubscriptionInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [upgrading, setUpgrading] = useState<string | null>(null)

  useEffect(() => {
    api.getSubscription()
      .then(setSub)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleUpgrade = async (tier: string) => {
    setUpgrading(tier)
    try {
      const { checkout_url } = await api.createCheckout(tier)
      window.location.href = checkout_url
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Failed to start checkout')
      setUpgrading(null)
    }
  }

  const handleManage = async () => {
    try {
      const { portal_url } = await api.getBillingPortal()
      window.location.href = portal_url
    } catch (err) {
      toast('error', err instanceof Error ? err.message : 'Failed to open billing portal')
    }
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-gray-400">Loading billing info...</div>
      </div>
    )
  }

  const currentTier = sub?.tier || 'free'
  const status = sub?.subscription_status

  return (
    <div className="flex-1 overflow-y-auto p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Billing & Plan</h1>

      {/* Current plan card */}
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 mb-8">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <CreditCard className="w-5 h-5 text-veil-400" />
            <h2 className="text-lg font-semibold">Current Plan</h2>
          </div>
          {status === 'active' && (
            <span className="flex items-center gap-1 text-sm text-green-400">
              <CheckCircle className="w-4 h-4" /> Active
            </span>
          )}
          {status === 'past_due' && (
            <span className="flex items-center gap-1 text-sm text-amber-400">
              <AlertTriangle className="w-4 h-4" /> Past Due
            </span>
          )}
        </div>

        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-3xl font-bold">{TIER_NAMES[currentTier] || currentTier}</span>
          {currentTier !== 'free' && <span className="text-gray-400">plan</span>}
        </div>

        {sub?.billing_email && (
          <p className="text-sm text-gray-400 mb-4">Billing email: {sub.billing_email}</p>
        )}

        <div className="flex flex-wrap gap-2 mb-4">
          {(TIER_FEATURES[currentTier] || []).map((f) => (
            <span key={f} className="px-2 py-1 bg-gray-700 rounded text-xs text-gray-300">{f}</span>
          ))}
        </div>

        {sub?.has_subscription && (
          <button
            onClick={handleManage}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-colors"
          >
            <ExternalLink className="w-4 h-4" />
            Manage Subscription
          </button>
        )}
      </div>

      {/* Upgrade options */}
      {(currentTier === 'free' || currentTier === 'solo') && (
        <>
          <h2 className="text-lg font-semibold mb-4">Upgrade your plan</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Solo */}
            {currentTier === 'free' && (
              <div className="bg-gray-800 border border-veil-600 rounded-xl p-6 relative">
                <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-veil-600 text-white text-[10px] font-semibold px-2.5 py-0.5 rounded-full">Most Popular</span>
                <h3 className="text-xl font-bold mb-1">Solo</h3>
                <div className="flex items-baseline gap-1 mb-1">
                  <span className="text-2xl font-bold">{TIER_PRICES.solo}</span>
                  <span className="text-sm text-gray-400">/mo</span>
                </div>
                <p className="text-gray-400 text-sm mb-4">For individual professionals</p>
                <ul className="space-y-2 mb-6">
                  {(TIER_FEATURES.solo ?? []).map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                      <CheckCircle className="w-3.5 h-3.5 text-veil-400 shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => handleUpgrade('solo')}
                  disabled={upgrading !== null}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-veil-600 hover:bg-veil-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
                >
                  {upgrading === 'solo' ? 'Redirecting...' : (
                    <>Get Solo <ArrowUpRight className="w-4 h-4" /></>
                  )}
                </button>
              </div>
            )}

            {/* Team */}
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
              <h3 className="text-xl font-bold mb-1">Team</h3>
              <div className="flex items-baseline gap-1 mb-1">
                <span className="text-2xl font-bold">{TIER_PRICES.team}</span>
                <span className="text-sm text-gray-400">/user/mo</span>
              </div>
              <p className="text-gray-400 text-sm mb-4">For growing teams</p>
              <ul className="space-y-2 mb-6">
                {(TIER_FEATURES.team ?? []).map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                    <CheckCircle className="w-3.5 h-3.5 text-veil-400 shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => handleUpgrade('team')}
                disabled={upgrading !== null}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-veil-600 hover:bg-veil-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
              >
                {upgrading === 'team' ? 'Redirecting...' : (
                  <>Upgrade to Team <ArrowUpRight className="w-4 h-4" /></>
                )}
              </button>
            </div>

            {/* Business */}
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
              <h3 className="text-xl font-bold mb-1">Business</h3>
              <div className="flex items-baseline gap-1 mb-1">
                <span className="text-2xl font-bold">{TIER_PRICES.business}</span>
                <span className="text-sm text-gray-400">/user/mo</span>
              </div>
              <p className="text-gray-400 text-sm mb-4">For regulated industries</p>
              <ul className="space-y-2 mb-6">
                {(TIER_FEATURES.business ?? []).map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                    <CheckCircle className="w-3.5 h-3.5 text-veil-400 shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              <button
                onClick={() => handleUpgrade('business')}
                disabled={upgrading !== null}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-veil-600 hover:bg-veil-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
              >
                {upgrading === 'business' ? 'Redirecting...' : (
                  <>Upgrade to Business <ArrowUpRight className="w-4 h-4" /></>
                )}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Enterprise CTA */}
      <div className="mt-8 bg-gray-800/50 border border-gray-700 rounded-xl p-6 text-center">
        <h3 className="font-semibold mb-2">Need Enterprise?</h3>
        <p className="text-sm text-gray-400 mb-4">
          Unlimited users, custom NER models, priority support, and dedicated infrastructure.
        </p>
        <a
          href="mailto:hello@veilproxy.ai?subject=Enterprise%20Inquiry"
          className="inline-flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm transition-colors"
        >
          Contact Sales
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>
    </div>
  )
}
