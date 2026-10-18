import { useState, useEffect } from 'react'
import { api, formatNumber, formatPct, formatShares, formatMoney } from '../lib/api'
import { useT } from '../lib/i18n'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, ReferenceLine,
} from 'recharts'

const BUCKET_COLORS: Record<string, string> = {
  deep_underwater: '#16a34a',
  underwater: '#22c55e',
  at_cost: '#94a3b8',
  moderate_profit: '#facc15',
  good_profit: '#f97316',
  heavy_profit: '#dc2626',
}

const INVESTOR_COLORS = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#6366f1', '#ef4444']

const PRESSURE_BADGE: Record<string, string> = {
  heavy: 'badge-red',
  moderate: 'badge-yellow',
  low: 'badge-blue',
  underwater: 'badge-green',
  unknown: 'badge-gray',
}

export default function CostAnalysisTab({ stockCode }: { stockCode: string }) {
  const [data, setData] = useState<any>(null)
  const [scenarios, setScenarios] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const { t, lang, brokerName } = useT()

  useEffect(() => {
    Promise.all([
      api.getCostAnalysis(stockCode),
      api.getScenarioAnalysis(stockCode).catch(() => null),
    ]).then(([d, s]) => {
      setData(d)
      setScenarios(s)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [stockCode])

  if (loading) return <div className="text-center py-8 text-slate-400">{t('loading')}</div>
  if (!data || !data.shareholders?.length) {
    return (
      <div className="text-center py-12">
        <p className="text-4xl mb-4">📊</p>
        <p className="text-slate-500">{t('noAttributionData')}</p>
      </div>
    )
  }

  const { current_price, total_analyzed_shares, pressure_score, shareholders, cost_buckets, investor_type_breakdown, broker_concentration } = data

  // Score colors
  const scoreColor = pressure_score >= 70 ? 'text-red-600 bg-red-50 border-red-200'
    : pressure_score >= 50 ? 'text-orange-600 bg-orange-50 border-orange-200'
    : pressure_score >= 30 ? 'text-yellow-600 bg-yellow-50 border-yellow-200'
    : 'text-green-600 bg-green-50 border-green-200'

  const scoreLabel = pressure_score >= 70 ? t('pressureExtreme')
    : pressure_score >= 50 ? t('pressureHigh')
    : pressure_score >= 30 ? t('pressureModerate')
    : t('pressureLow')

  const scoreBarColor = pressure_score >= 70 ? '#dc2626'
    : pressure_score >= 50 ? '#f97316'
    : pressure_score >= 30 ? '#eab308'
    : '#22c55e'

  // Cost distribution chart data
  const bucketLabels: Record<string, string> = {
    deep_underwater: t('deepUnderwater'),
    underwater: t('underwater'),
    at_cost: t('atCost'),
    moderate_profit: t('moderateProfit'),
    good_profit: t('goodProfit'),
    heavy_profit: t('heavyProfit'),
  }

  const distData = cost_buckets
    .filter((b: any) => b.shares > 0)
    .map((b: any) => ({
      name: bucketLabels[b.bucket] || b.bucket,
      key: b.bucket,
      shares: Math.round(b.shares / 10000),
      sharesRaw: b.shares,
      pct: b.pct_of_total,
      holders: b.main_shareholders.join(', '),
    }))

  // Shareholder cost scatter/bar data
  const shChartData = shareholders
    .filter((s: any) => s.cost_hkd && s.cost_hkd > 0 && s.shares_current > 0)
    .map((s: any) => ({
      name: s.name.length > 8 ? s.name.slice(0, 8) + '…' : s.name,
      fullName: s.name,
      cost: s.cost_hkd,
      shares: s.shares_current,
      sharesWan: Math.round(s.shares_current / 10000),
      type: s.investor_type,
      profitPct: s.profit_pct,
    }))

  // Investor type pie data
  const pieData = investor_type_breakdown.map((it: any) => ({
    name: it.investor_type,
    value: it.shares,
    pct: it.pct,
  }))

  // Broker concentration data
  const brokerData = broker_concentration.slice(0, 15).map((b: any) => ({
    name: brokerName(b.participant_id, b.participant_name).slice(0, 18),
    fullName: brokerName(b.participant_id, b.participant_name),
    count: b.shareholder_count,
    shares: b.total_shares,
  }))

  return (
    <div className="space-y-6">
      {/* Summary Card */}
      <div className={`card ${scoreColor} border-2`}>
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-6 flex-wrap">
              <div>
                <div className="text-sm opacity-70">{t('currentPrice')}</div>
                <div className="text-3xl font-bold mt-1">HK${current_price?.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-sm opacity-70">{t('totalAnalyzedShares')}</div>
                <div className="text-2xl font-bold mt-1">{formatShares(total_analyzed_shares)}</div>
              </div>
              <div>
                <div className="text-sm opacity-70">{t('pressureScore')}</div>
                <div className="flex items-baseline gap-2">
                  <div className="text-4xl font-bold">{pressure_score}</div>
                  <div className="text-sm font-medium">/100</div>
                </div>
                <div className="text-sm font-medium mt-1">{scoreLabel}</div>
              </div>
            </div>
          </div>
          <div className="text-right text-sm opacity-70">
            <div>{shareholders.length} {t('shareholder')}</div>
            <div>{broker_concentration.length} {t('broker')}</div>
          </div>
        </div>
        <div className="mt-4 h-3 bg-white/50 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${pressure_score}%`, background: scoreBarColor }}
          />
        </div>
        <div className="flex justify-between text-xs mt-1 opacity-60">
          <span>0 {t('pressureLow')}</span>
          <span>50 {t('pressureModerate')}</span>
          <span>100 {t('pressureExtreme')}</span>
        </div>
      </div>

      {/* Cost Distribution Bar Chart */}
      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">💰 {t('costDistribution')}</h3>
        {distData.length > 0 ? (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={distData} layout="vertical" margin={{ left: 20, right: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v: number) => formatNumber(v * 10000)} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={90} />
              <Tooltip
                formatter={(value: number, name: string, props: any) => [
                  `${formatShares(props.payload.sharesRaw)} (${props.payload.pct}%)`,
                  props.payload.name,
                ]}
                labelFormatter={() => t('holdings')}
              />
              <Bar dataKey="shares" radius={[0, 4, 4, 0]}>
                {distData.map((entry: any, i: number) => (
                  <Cell key={i} fill={BUCKET_COLORS[entry.key] || '#94a3b8'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-center py-8 text-slate-400">{t('noCostData')}</div>
        )}
      </div>

      {/* Two-column charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Investor Type Pie */}
        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-4">🥧 {t('investorTypePie')}</h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={(entry: any) => `${entry.name} ${entry.pct}%`}
                  labelLine={false}
                >
                  {pieData.map((_: any, i: number) => (
                    <Cell key={i} fill={INVESTOR_COLORS[i % INVESTOR_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => formatShares(value)} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-8 text-slate-400">{t('noData')}</div>
          )}
        </div>

        {/* Broker Concentration */}
        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-4">🏦 {t('brokerConcentration')}</h3>
          {brokerData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={brokerData} layout="vertical" margin={{ left: 20, right: 30 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={100} />
                <Tooltip
                  formatter={(value: number, n: string, props: any) => [
                    `${value} ${t('shareholderCount')} · ${formatShares(props.payload.shares)}`,
                    props.payload.fullName,
                  ]}
                />
                <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-8 text-slate-400">{t('noData')}</div>
          )}
        </div>
      </div>

      {/* Shareholder Cost Chart */}
      {shChartData.length > 0 && (
        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-4">📊 {t('shareholderCostChart')}</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={shChartData} margin={{ bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 10, angle: -35, textAnchor: 'end' } as any}
                height={80}
                interval={0}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                label={{ value: t('costPrice'), angle: -90, position: 'insideLeft', fontSize: 12 }}
              />
              <Tooltip
                formatter={(value: number, name: string, props: any) => [
                  `HK$${value?.toFixed(2)} | ${formatShares(props.payload.shares)}`,
                  props.payload.fullName,
                ]}
              />
              <ReferenceLine
                y={current_price}
                stroke="#dc2626"
                strokeDasharray="5 5"
                strokeWidth={2}
                label={{ value: `HK$${current_price?.toFixed(2)}`, fill: '#dc2626', fontSize: 11, position: 'right' }}
              />
              <Bar dataKey="cost" radius={[4, 4, 0, 0]}>
                {shChartData.map((entry: any, i: number) => {
                  const typeColorMap: Record<string, string> = {
                    'Pre-IPO': '#8b5cf6',
                    'Cornerstone': '#3b82f6',
                    'Management': '#f59e0b',
                    'ESOP': '#ec4899',
                    'Public': '#10b981',
                  }
                  return <Cell key={i} fill={typeColorMap[entry.type] || '#6366f1'} />
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-3 flex-wrap text-xs text-slate-500 mt-2">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block" style={{background:'#8b5cf6'}}></span>Pre-IPO</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block" style={{background:'#3b82f6'}}></span>Cornerstone</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block" style={{background:'#f59e0b'}}></span>Management</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block" style={{background:'#ec4899'}}></span>ESOP</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block" style={{background:'#10b981'}}></span>Public</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm inline-block" style={{background:'#6366f1'}}></span>Other</span>
            <span className="text-red-600">─── {lang === 'en' ? 'Current Price' : '当前价'}</span>
          </div>
        </div>
      )}

      {/* Shareholder Table */}
      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">📋 {t('shareholderList')}</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b">
                <th className="py-2">{t('shareholder')}</th>
                <th className="py-2 text-right">{t('cost')}</th>
                <th className="py-2 text-right">{t('currentPrice')}</th>
                <th className="py-2 text-right">{t('profitPct')}</th>
                <th className="py-2 text-right">{t('holdings')}</th>
                <th className="py-2 text-right">{t('floatingPnL')}</th>
                <th className="py-2">{t('pressureLevel')}</th>
                <th className="py-2">{t('broker')}</th>
              </tr>
            </thead>
            <tbody>
              {shareholders.map((s: any, i: number) => {
                const profitColor = s.profit_pct == null ? 'text-slate-400'
                  : s.profit_pct > 50 ? 'text-red-600 font-semibold'
                  : s.profit_pct >= 20 ? 'text-orange-600'
                  : s.profit_pct >= 0 ? 'text-yellow-600'
                  : 'text-green-600'
                const pressureLabel: Record<string, string> = {
                  heavy: t('pressureHeavy'),
                  moderate: t('pressureModerateLevel'),
                  low: t('pressureLowLevel'),
                  underwater: t('pressureUnderwater'),
                  unknown: t('pressureUnknown'),
                }
                return (
                  <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-2">
                      <div className="font-medium text-slate-800">{s.name}</div>
                      <div className="text-xs text-slate-400">{s.investor_type}</div>
                    </td>
                    <td className="py-2 text-right font-mono">
                      {s.cost_hkd ? `HK$${s.cost_hkd.toFixed(2)}` : '-'}
                    </td>
                    <td className="py-2 text-right font-mono">HK${current_price?.toFixed(2)}</td>
                    <td className={`py-2 text-right font-mono ${profitColor}`}>
                      {s.profit_pct != null ? formatPct(s.profit_pct) : '-'}
                    </td>
                    <td className="py-2 text-right font-mono">{formatShares(s.shares_current)}</td>
                    <td className={`py-2 text-right font-mono ${s.floating_profit != null && s.floating_profit >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {s.floating_profit != null ? formatMoney(s.floating_profit) : '-'}
                    </td>
                    <td className="py-2">
                      <span className={`badge ${PRESSURE_BADGE[s.pressure_level] || 'badge-gray'}`}>
                        {pressureLabel[s.pressure_level] || s.pressure_level}
                      </span>
                    </td>
                    <td className="py-2">
                      <div className="text-slate-700">{brokerName(s.participant_id, s.participant_name)}</div>
                      <div className="text-xs text-slate-400 font-mono">{s.participant_id}</div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Scenario Analysis */}
      {scenarios && scenarios.scenarios && (
        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-4">
            {lang === 'en' ? '🔮 Selling Pressure Scenarios' : '🔮 减持压力情景分析'}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {['optimistic', 'base', 'pessimistic'].map((key) => {
              const sc = scenarios.scenarios[key]
              if (!sc) return null
              const cardColor = key === 'optimistic' ? 'border-green-200 bg-green-50/30'
                : key === 'base' ? 'border-yellow-200 bg-yellow-50/30'
                : 'border-red-200 bg-red-50/30'
              const numColor = key === 'optimistic' ? 'text-green-700' : key === 'base' ? 'text-yellow-700' : 'text-red-700'
              const name = lang === 'en' ? sc.name_en : sc.name_zh
              const desc = lang === 'en' ? sc.description_en : sc.description_zh
              const assumptions = lang === 'en' ? sc.assumptions_en : sc.assumptions_zh
              const sharesLabel = lang === 'en' ? 'Potential Selling' : '预计减持'
              const absorbLabel = lang === 'en' ? 'Days to Absorb' : '消化天数'
              const impactLabel = lang === 'en' ? 'Est. Price Impact' : '预估冲击'
              return (
                <div key={key} className={`p-4 rounded-lg border ${cardColor}`}>
                  <h4 className="font-bold text-lg mb-2">{name}</h4>
                  <p className="text-sm text-slate-600 mb-3">{desc}</p>
                  <div className="space-y-2 mb-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">{sharesLabel}</span>
                      <span className={`font-bold ${numColor}`}>{(sc.estimated_sell_shares/10000).toFixed(0)}{t('tenKSharesShort')} ({sc.pct_of_freefloat}%)</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">{absorbLabel}</span>
                      <span className="font-semibold">{sc.days_to_absorb}{t('daysUnit')}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-500">{impactLabel}</span>
                      <span className={`font-bold ${numColor}`}>{sc.price_impact_pct > 0 ? '+' : ''}{sc.price_impact_pct}%</span>
                    </div>
                  </div>
                  <div className="text-xs text-slate-500 space-y-1 border-t pt-2">
                    {assumptions.map((a: string, i: number) => <div key={i}>• {a}</div>)}
                  </div>
                </div>
              )
            })}
          </div>
          <p className="text-xs text-slate-400 mt-3">{t('scenarioFootnote')}</p>
        </div>
      )}
    </div>
  )
}
