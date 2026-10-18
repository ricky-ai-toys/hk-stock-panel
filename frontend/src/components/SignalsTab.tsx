import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { useT } from '../lib/i18n'

export default function SignalsTab({ stockCode }: { stockCode: string }) {
  const [signals, setSignals] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const { t, brokerName } = useT()

  useEffect(() => {
    api.getSignals(stockCode).then(d => {
      setSignals(d)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [stockCode])

  if (loading) return <div className="text-center py-8 text-slate-400">{t('loading')}</div>
  if (!signals) return <div className="text-center py-8 text-slate-400">{t('noData')}</div>

  const scoreColor = signals.score >= 75 ? 'text-red-600 bg-red-50 border-red-200'
    : signals.score >= 60 ? 'text-orange-600 bg-orange-50 border-orange-200'
    : signals.score <= 25 ? 'text-green-600 bg-green-50 border-green-200'
    : signals.score <= 40 ? 'text-emerald-600 bg-emerald-50 border-emerald-200'
    : 'text-slate-600 bg-slate-50 border-slate-200'

  return (
    <div className="space-y-6">
      {/* Score Gauge */}
      <div className={`card ${scoreColor} border-2`}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm opacity-70">{t('signalScoreLabel')}</div>
            <div className="text-5xl font-bold mt-1">{signals.score}</div>
            <div className="text-lg font-medium mt-2">{signals.verdict}</div>
          </div>
          <div className="text-right text-sm">
            <div className="text-red-600">{t('sellSignals')}: {signals.sell_signals}</div>
            <div className="text-green-600 mt-1">{t('buySignals')}: {signals.buy_signals}</div>
          </div>
        </div>
        <div className="mt-4 h-3 bg-white/50 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${signals.score}%`,
              background: signals.score >= 60 ? '#ef4444' : signals.score <= 40 ? '#22c55e' : '#eab308',
            }}
          />
        </div>
        <div className="flex justify-between text-xs mt-1 opacity-60">
          <span>0 {t('strongAccumulation')}</span>
          <span>50 {t('neutral')}</span>
          <span>100 {t('strongDistribution')}</span>
        </div>
      </div>

      {/* Anomaly List */}
      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">{t('detectedAnomalies')}</h3>
        {signals.anomalies?.length > 0 ? (
          <div className="space-y-3">
            {signals.anomalies.map((a: any, i: number) => {
              const sevStyle = a.severity === 'high'
                ? 'border-l-4 border-red-500 bg-red-50'
                : 'border-l-4 border-yellow-500 bg-yellow-50'
              return (
                <div key={i} className={`p-3 rounded-r ${sevStyle}`}>
                  <div className="flex items-start justify-between">
                    <div>
                      <span className={`badge ${a.severity === 'high' ? 'badge-red' : 'badge-yellow'} mr-2`}>
                        {a.severity === 'high' ? t('highPriority') : t('midPriority')}
                      </span>
                      <span className="badge badge-gray mr-2">{a.type}</span>
                      {a.shareholder_name && (
                        <span className="badge badge-blue">{a.shareholder_name}</span>
                      )}
                    </div>
                    {a.change_pct_of_issued && (
                      <span className="text-sm font-mono text-slate-600">
                        {a.change_pct_of_issued}%
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-700 mt-2">{a.message}</p>
                  {a.participant_name && (
                    <p className="text-xs text-slate-500 mt-1 font-mono">{a.participant_id} · {brokerName(a.participant_id, a.participant_name)}</p>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-center py-8 text-slate-400">
            <p className="text-3xl mb-2">✅</p>
            <p>{t('noAnomalies')}</p>
          </div>
        )}
      </div>

      {/* Signal Explanation */}
      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-3">{t('signalExplanation')}</h3>
        <div className="text-sm text-slate-600 space-y-2">
          <p dangerouslySetInnerHTML={{ __html: t('scoreLogic') }} />
          <p dangerouslySetInnerHTML={{ __html: t('highPriorityAnomaly') }} />
          <p dangerouslySetInnerHTML={{ __html: t('newParticipant') }} />
          <p dangerouslySetInnerHTML={{ __html: t('participantExit') }} />
          <p dangerouslySetInnerHTML={{ __html: t('volumeAnomaly') }} />
          <p className="text-slate-400 mt-3">{t('signalDisclaimer')}</p>
        </div>
      </div>
    </div>
  )
}
