import { useState, useEffect } from 'react'
import { api, formatShares, formatMoney } from '../lib/api'
import { useT } from '../lib/i18n'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell,
  ComposedChart, ReferenceLine,
} from 'recharts'

const FLOW_COLORS = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#14b8a6']

export default function CapitalFlowTab({ stockCode }: { stockCode: string }) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(1)
  const [endDate, setEndDate] = useState<string>('')
  const { t, lang, brokerName } = useT()

  const load = async (d: number, ed?: string) => {
    setLoading(true)
    try {
      const res = await api.getCapitalFlow(stockCode, d, ed || undefined)
      setData(res)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(days, endDate) }, [stockCode, days, endDate])

  if (loading) return <div className="text-center py-8 text-slate-400">{t('loading')}</div>
  if (!data || (!data.top_inflows?.length && !data.top_outflows?.length && !data.shareholder_flows?.length)) {
    return (
      <div className="text-center py-12">
        <p className="text-4xl mb-4">🌊</p>
        <p className="text-slate-500">{t('noFlowData')}</p>
      </div>
    )
  }

  const { top_inflows, top_outflows, daily_flows, top_brokers, top_broker_meta, shareholder_flows, period_start, period_end, available_dates } = data

  // Prepare stacked bar chart data.
  // New API: daily_flows use participant_id as stable keys and top_broker_meta carries labels.
  // Old API fallback: top_brokers are already display-name keys.
  const brokerMeta = top_broker_meta || top_brokers?.map((name: string) => ({ pid: name, label: name })) || []
  const pidLabelMap: Record<string, string> = {}
  for (const b of brokerMeta) {
    pidLabelMap[b.pid] = brokerName(b.pid, b.label || b.participant_name) || b.pid
  }
  const chartData = daily_flows.map((d: any) => {
    const entry: any = { date: d.date?.slice(5) }
    for (const b of brokerMeta) {
      const v = Math.round((d[b.pid] || 0) / 10000)
      entry[b.pid + '_pos'] = v > 0 ? v : 0
      entry[b.pid + '_neg'] = v < 0 ? v : 0
    }
    return entry
  })

  // Aggregate daily net flow (sum all tracked brokers for the day) — daily frequency chart
  const dailyNetData = daily_flows.map((d: any) => {
    let total = 0
    for (const b of brokerMeta) {
      total += (d[b.pid] || 0)
    }
    const net = Math.round(total / 10000)
    return {
      date: d.date?.slice(5),
      net,
      inflow: net > 0 ? net : 0,
      outflow: net < 0 ? net : 0,
    }
  })
  const totalPeriodNet = dailyNetData.reduce((s, r) => s + r.net, 0)
  const netAbsMax = Math.max(1, ...dailyNetData.map(d => Math.abs(d.net)))
  const netDomain: [number, number] = [-Math.ceil(netAbsMax * 1.1 / 5) * 5, Math.ceil(netAbsMax * 1.1 / 5) * 5]

  return (
    <div className="space-y-6">
      {/* Header with period selector */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">🌊 {t('capitalFlow')}</h2>
          <p className="text-sm text-slate-500">
            {t('periodRange')}: {period_start} ~ {period_end}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs font-medium text-slate-500">{t('periodRange')}</span>
          {/* End-date picker to inspect historical windows */}
          <label className="flex items-center gap-2 text-sm text-slate-500">
            <span>{t('periodEnd')}</span>
            <select
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
              className="px-2 py-1.5 border border-slate-300 rounded-md text-sm bg-white"
            >
              <option value="">{t('latestDate')}</option>
              {(available_dates || []).map((dt: string) => (
                <option key={dt} value={dt}>{dt}</option>
              ))}
            </select>
          </label>
          {[1, 5, 10, 20, 60].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1 text-sm rounded-md border transition-colors ${
                days === d ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
              }`}
            >
              {d}D
            </button>
          ))}
        </div>
      </div>

      {/* Top Inflows / Outflows Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Inflows */}
        <div className="card">
          <h3 className="font-semibold text-red-600 mb-4">📈 {t('topInflows')}</h3>
          {top_inflows?.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b">
                    <th className="py-2">{t('broker')}</th>
                    <th className="py-2">{t('attributedShareholder')}</th>
                    <th className="py-2 text-right">{t('netChange')}</th>
                    <th className="py-2 text-right">{t('currentShares')}</th>
                  </tr>
                </thead>
                <tbody>
                  {top_inflows.map((b: any, i: number) => (
                    <tr key={i} className="border-b border-slate-100 hover:bg-red-50/30">
                      <td className="py-2">
                        <div className="font-medium text-slate-800 text-xs">{brokerName(b.participant_id, b.participant_name)}</div>
                        <div className="text-xs text-slate-400 font-mono">{b.participant_id}</div>
                      </td>
                      <td className="py-2">
                        {b.attributed_shareholder ? (
                          <span className="badge badge-blue">{b.attributed_shareholder}</span>
                        ) : (
                          <span className="text-xs text-slate-400">{t('unknownRetail')}</span>
                        )}
                      </td>
                      <td className="py-2 text-right font-mono text-red-600 font-semibold">
                        +{formatShares(b.net_change)}
                      </td>
                      <td className="py-2 text-right font-mono text-slate-600">
                        {formatShares(b.current_shares)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-6 text-slate-400 text-sm">-</div>
          )}
        </div>

        {/* Top Outflows */}
        <div className="card">
          <h3 className="font-semibold text-green-600 mb-4">📉 {t('topOutflows')}</h3>
          {top_outflows?.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b">
                    <th className="py-2">{t('broker')}</th>
                    <th className="py-2">{t('attributedShareholder')}</th>
                    <th className="py-2 text-right">{t('netChange')}</th>
                    <th className="py-2 text-right">{t('currentShares')}</th>
                  </tr>
                </thead>
                <tbody>
                  {top_outflows.map((b: any, i: number) => (
                    <tr key={i} className="border-b border-slate-100 hover:bg-green-50/30">
                      <td className="py-2">
                        <div className="font-medium text-slate-800 text-xs">{brokerName(b.participant_id, b.participant_name)}</div>
                        <div className="text-xs text-slate-400 font-mono">{b.participant_id}</div>
                      </td>
                      <td className="py-2">
                        {b.attributed_shareholder ? (
                          <span className="badge badge-blue">{b.attributed_shareholder}</span>
                        ) : (
                          <span className="text-xs text-slate-400">{t('unknownRetail')}</span>
                        )}
                      </td>
                      <td className="py-2 text-right font-mono text-green-600 font-semibold">
                        {formatShares(b.net_change)}
                      </td>
                      <td className="py-2 text-right font-mono text-slate-600">
                        {formatShares(b.current_shares)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-6 text-slate-400 text-sm">-</div>
          )}
        </div>
      </div>

      {/* Daily Net Flow (aggregate) */}
      {dailyNetData.length > 0 && (
        <div className="card">
          <div className="flex items-end justify-between flex-wrap gap-2 mb-3">
            <h3 className="font-semibold text-slate-800">📈 {t('dailyNetFlow')}</h3>
            <div className="text-xs text-slate-500">
              {t('periodRange')} {t('netChange')}:{' '}
              <span className={`font-semibold font-mono ${totalPeriodNet > 0 ? 'text-red-600' : totalPeriodNet < 0 ? 'text-green-600' : 'text-slate-500'}`}>
                {totalPeriodNet > 0 ? '+' : ''}{totalPeriodNet.toLocaleString()}{t('tenKShares')}
              </span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={dailyNetData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis domain={netDomain} tick={{ fontSize: 11 }} tickFormatter={(v: number) => lang === 'en' ? `${v * 10}K` : `${v}${t('tenKUnit')}`} />
              <Tooltip
                formatter={(value: number, name: string) => {
                  const v = Number(value)
                  if (!v) return ['', '']
                  const label = name === 'inflow' ? t('netChange') : t('netChange')
                  return [`${v > 0 ? '+' : ''}${v.toLocaleString()}${t('tenKShares')}`, label]
                }}
              />
              <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
              <Bar dataKey="inflow" fill="#ef4444" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="outflow" fill="#10b981" radius={[0, 0, 3, 3]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-slate-400 mt-2">{t('dailyNetFlowHint')}</p>
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 text-xs">
            {dailyNetData.map((d: any) => (
              <div key={d.date} className="flex justify-between items-center px-2 py-1.5 bg-slate-50 rounded border border-slate-100">
                <span className="text-slate-500">{d.date}</span>
                <span className={`font-mono font-semibold ${d.net > 0 ? 'text-red-600' : d.net < 0 ? 'text-green-600' : 'text-slate-400'}`}>
                  {d.net > 0 ? '+' : ''}{d.net}{t('tenKShares')}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Daily Stacked Bar Chart */}
      {chartData.length > 0 && brokerMeta.length > 0 && (
        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-4">📊 {t('dailyBrokerFlows')}</h3>
          <ResponsiveContainer width="100%" height={Math.min(260 + brokerMeta.length * 6, 400)}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis domain={[Math.min(0, ...chartData.map((d: any) => brokerMeta.reduce((s: number, b: any) => s + (d[b.pid + '_neg'] || 0), 0))), Math.max(0, ...chartData.map((d: any) => brokerMeta.reduce((s: number, b: any) => s + (d[b.pid + '_pos'] || 0), 0)))]} tick={{ fontSize: 11 }} tickFormatter={(v: number) => lang === 'en' ? `${v * 10}K` : `${v}${t('tenKUnit')}`} />
              <Tooltip
                formatter={(value: number, name: string) => {
                  if (!value) return ['', '']
                  const pid = name.replace(/_pos$/, '').replace(/_neg$/, '')
                  return [`${value > 0 ? '+' : ''}${value}${t('tenKShares')}`, pidLabelMap[pid] || pid]
                }}
              />
              <Legend
                wrapperStyle={{ fontSize: 11 }}
                formatter={(value: string) => pidLabelMap[value.replace(/_pos$/, '').replace(/_neg$/, '')] || value}
              />
              {brokerMeta.map((b: any, i: number) => (
                <Bar
                  key={b.pid + '_pos'}
                  dataKey={b.pid + '_pos'}
                  stackId="pos"
                  fill={FLOW_COLORS[i % FLOW_COLORS.length]}
                  name={b.pid + '_pos'}
                  isAnimationActive={false}
                />
              ))}
              {brokerMeta.map((b: any, i: number) => (
                <Bar
                  key={b.pid + '_neg'}
                  dataKey={b.pid + '_neg'}
                  stackId="neg"
                  fill={FLOW_COLORS[i % FLOW_COLORS.length]}
                  name={b.pid + '_neg'}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-slate-400 mt-2">{t('positiveHint')}。{t('dailyBrokerFlows')}</p>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-xs border border-slate-100 rounded-lg overflow-hidden">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-2 py-2 text-left">{t('date')}</th>
                  {brokerMeta.slice(0, 8).map((b: any) => (
                    <th key={b.pid} className="px-2 py-2 text-right whitespace-nowrap">{pidLabelMap[b.pid]?.slice(0, 14) || b.pid}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {daily_flows.map((d: any) => (
                  <tr key={d.date} className="border-t border-slate-100">
                    <td className="px-2 py-2 font-mono text-slate-500">{d.date?.slice(5)}</td>
                    {brokerMeta.slice(0, 8).map((b: any) => {
                      const v = Math.round((d[b.pid] || 0) / 10000)
                      return (
                        <td key={b.pid} className={`px-2 py-2 text-right font-mono ${v > 0 ? 'text-red-600' : v < 0 ? 'text-green-600' : 'text-slate-300'}`}>
                          {v ? `${v > 0 ? '+' : ''}${v}` : '—'}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Shareholder Flow Visualization (CSS-based) */}
      {shareholder_flows?.length > 0 && (
        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-4">🔀 {t('shareholderFlow')}</h3>
          <div className="space-y-1">
            {/* Header row */}
            <div className="grid grid-cols-12 gap-2 text-xs font-semibold text-slate-500 pb-2 border-b">
              <div className="col-span-4">{t('shareholder')}</div>
              <div className="col-span-4 text-center">{t('broker')}</div>
              <div className="col-span-4 text-right">{t('netChange')}</div>
            </div>
            {shareholder_flows.map((sf: any, i: number) => {
              const isSelling = sf.net_change < 0
              const isBuying = sf.net_change > 0
              const dirColor = isSelling ? 'text-green-600' : isBuying ? 'text-red-600' : 'text-slate-400'
              const arrow = isSelling ? '▼' : isBuying ? '▲' : '─'
              const arrowBg = isSelling ? 'bg-green-100 border-green-200' : isBuying ? 'bg-red-100 border-red-200' : 'bg-slate-100 border-slate-200'

              return (
                <div key={i} className="grid grid-cols-12 gap-2 items-center py-2 border-b border-slate-50 relative">
                  {/* Shareholder */}
                  <div className="col-span-4">
                    <div className="font-medium text-slate-800 text-sm">{sf.shareholder_name}</div>
                    <div className="text-xs text-slate-400">
                      <span className="badge badge-gray mr-1">{sf.investor_type}</span>
                      {formatShares(sf.shares_current)}
                    </div>
                  </div>

                  {/* Flow connector */}
                  <div className="col-span-4 flex items-center justify-center">
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md border ${arrowBg} text-xs w-full justify-center`}>
                      <div className="h-0.5 bg-slate-300 flex-1 max-w-8"></div>
                      <div className="text-slate-700 font-mono text-center">
                        <div className="text-slate-800 font-medium text-xs">{brokerName(sf.participant_id, sf.participant_name).slice(0, 24)}</div>
                        <div className="text-slate-400">{sf.participant_id}</div>
                      </div>
                      <div className="h-0.5 bg-slate-300 flex-1 max-w-8"></div>
                    </div>
                  </div>

                  {/* Direction */}
                  <div className="col-span-4 text-right">
                    <div className={`inline-flex items-center gap-1 font-mono font-semibold ${dirColor}`}>
                      <span className="text-lg">{arrow}</span>
                      <span>
                        {isBuying ? '+' : ''}{formatShares(sf.net_change)}
                      </span>
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      {sf.shares_baseline > 0 && (
                        <span>{t('currentShares')}: {formatShares(sf.shares_current)}</span>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
