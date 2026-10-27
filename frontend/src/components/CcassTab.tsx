import { useState, useEffect, useRef } from 'react'
import { api, formatShares } from '../lib/api'
import { useT } from '../lib/i18n'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const CCASS_DAY_OPTIONS = [30, 60, 90, 180, 365]

function axisInterval(count: number) {
  if (count <= 40) return 0
  return Math.max(0, Math.ceil(count / 8) - 1)
}

export default function CcassTab({ stockCode }: { stockCode: string }) {
  const [participants, setParticipants] = useState<any[]>([])
  const [hkConnect, setHkConnect] = useState<any[]>([])
  const [totals, setTotals] = useState<any[]>([])
  const [selectedDate, setSelectedDate] = useState<string>('')
  const [dates, setDates] = useState<string[]>([])
  const [days, setDays] = useState(60)
  const [coverage, setCoverage] = useState<any>(null)
  const [backfillProgress, setBackfillProgress] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState<'all' | 'changes'>('all')
  const [exporting, setExporting] = useState(false)
  const { t, brokerName } = useT()
  const loadSeq = useRef(0)

  const load = async () => {
    const seq = ++loadSeq.current
    setLoading(true)
    try {
      const [datesRes, pRes, cRes, hkRes, totalRes, cov] = await Promise.all([
        api.getDates(stockCode, days),
        api.getParticipants(stockCode, selectedDate || undefined),
        api.getChanges(stockCode, selectedDate || undefined),
        api.getHkConnect(stockCode, days),
        api.getCcassTotal(stockCode, days),
        api.ensureCcassRange(stockCode, days).catch(() => null),
      ])
      if (seq !== loadSeq.current) return
      setHkConnect(Array.isArray(hkRes) ? hkRes : [])
      setTotals(Array.isArray(totalRes) ? totalRes : [])
      setDates(datesRes.dates || [])
      setCoverage(cov)

      const changesMap: Record<string, any> = {}
      cRes.changes?.forEach((c: any) => { changesMap[c.participant_id] = c })
      const merged = pRes.participants?.map((p: any) => ({
        ...p,
        shares_change: changesMap[p.participant_id]?.shares_change ?? p.shares_change,
        shares_change_3d: changesMap[p.participant_id]?.shares_change_3d ?? p.shares_change_3d,
        shareholder_name: changesMap[p.participant_id]?.shareholder_name ?? p.shareholder_name,
      })) || []
      setParticipants(merged)
    } catch (e) {
      console.error(e)
    } finally {
      if (seq === loadSeq.current) setLoading(false)
    }
  }

  useEffect(() => { load() }, [stockCode, selectedDate, days])

  useEffect(() => {
    if (!coverage || coverage.backfill !== 'running' || !coverage.job_id) {
      setBackfillProgress(null)
      return
    }
    let cancelled = false
    let timer: number | undefined
    const poll = async () => {
      if (cancelled) return
      try {
        const status = await api.getJobStatus(coverage.job_id)
        if (cancelled) return
        if (typeof status.progress === 'number') setBackfillProgress(status.progress)
        if (status.status === 'done' || status.status === 'error') {
          load()
          return
        }
      } catch {
        // The job row can appear a moment after ensure returns.
      }
      if (!cancelled) timer = window.setTimeout(poll, 3000)
    }
    poll()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [coverage?.job_id, coverage?.backfill, stockCode, selectedDate, days])

  const handleExport = () => {
    setExporting(true)
    window.open(`/api/stock/${stockCode}/export`, '_blank')
    setTimeout(() => setExporting(false), 1000)
  }

  const netBuyLabel = t('netBuy')
  const holdingsLabel = t('ccassHoldings')
  const hkChartData = hkConnect.map((h: any) => ({
    date: h.trade_date?.slice(5),
    [netBuyLabel]: Math.round((h.shares_change || 0) / 10000),
  }))
  const totalChartData = totals.map((row: any) => ({
    date: row.trade_date?.slice(5),
    [holdingsLabel]: Math.round((row.total_shares || 0) / 10000),
  }))

  const filtered = participants
    .filter((p: any) => {
      if (viewMode === 'changes') return Math.abs(p.shares_change || 0) > 0
      return true
    })
    .sort((a: any, b: any) => {
      if (viewMode === 'all') return (b.shares || 0) - (a.shares || 0)
      return Math.abs(b.shares_change || 0) - Math.abs(a.shares_change || 0)
    })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-lg font-semibold text-slate-800">{t('tab_ccass')}</h2>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-medium text-slate-500">{t('ccassRange')}</span>
          {CCASS_DAY_OPTIONS.map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1 text-sm rounded-md border transition-colors ${
                days === d ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'
              }`}
            >
              {d}{t('daysUnit')}
            </button>
          ))}
        </div>
      </div>

      {coverage?.backfill === 'running' && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-2 rounded-lg text-sm">
          {t('ccassBackfillShort')}
          {backfillProgress != null ? ` ${backfillProgress}%` : ''}
        </div>
      )}

      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">{t('ccassHoldingsTrend')}</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={totalChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} interval={axisInterval(totalChartData.length)} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line type="monotone" dataKey={holdingsLabel} stroke="#2563eb" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Southbound bar chart */}
      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">{t('southboundDailyNet')}</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={hkChartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} interval={axisInterval(hkChartData.length)} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey={netBuyLabel} fill="#8b5cf6" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">{t('ccassDailyTable')}</h3>
        {totals.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-sm">{loading ? t('loading') : t('noCcassData')}</div>
        ) : (
          <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b">
                  <th className="py-2">{t('date')}</th>
                  <th className="py-2 text-right">{t('ccassHoldings')}</th>
                  <th className="py-2 text-right">{t('pct')}</th>
                  <th className="py-2 text-right">{t('southboundHoldings')}</th>
                  <th className="py-2 text-right">{t('dailyChange')}</th>
                </tr>
              </thead>
              <tbody>
                {[...totals].reverse().map((row: any) => (
                  <tr key={row.trade_date} className="border-b border-slate-100">
                    <td className="py-2 font-mono text-xs">{row.trade_date}</td>
                    <td className="py-2 text-right font-mono text-xs">{formatShares(row.total_shares)}</td>
                    <td className="py-2 text-right text-xs">{row.pct_of_issued != null ? `${Number(row.pct_of_issued).toFixed(2)}%` : '—'}</td>
                    <td className="py-2 text-right font-mono text-xs">{formatShares(row.hk_connect_shares)}</td>
                    <td className={`py-2 text-right font-mono text-xs ${
                      (row.hk_connect_change || 0) < 0 ? 'text-green-600' : (row.hk_connect_change || 0) > 0 ? 'text-red-600' : 'text-slate-400'
                    }`}>
                      {row.hk_connect_change != null ? (row.hk_connect_change > 0 ? '+' : '') + formatShares(row.hk_connect_change) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Participants Table */}
      <div className="card">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h3 className="font-semibold text-slate-800">{t('participantHoldings')}</h3>
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={handleExport} disabled={exporting} className="btn btn-secondary text-sm">
              {exporting ? t('exporting') : t('exportExcel')}
            </button>
            <select
              value={selectedDate}
              onChange={e => setSelectedDate(e.target.value)}
              className="text-sm border border-slate-300 rounded px-2 py-1"
            >
              <option value="">{t('latestDate')}</option>
              {dates.map(d => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            <div className="flex bg-slate-100 rounded-md p-0.5">
              {[
                { k: 'changes', l: t('showChanges') },
                { k: 'all', l: t('showAll') },
              ].map(v => (
                <button
                  key={v.k}
                  onClick={() => setViewMode(v.k as any)}
                  className={`px-3 py-1 text-sm rounded transition-colors ${
                    viewMode === v.k ? 'bg-white shadow text-slate-800' : 'text-slate-500'
                  }`}
                >
                  {v.l}
                </button>
              ))}
            </div>
          </div>
        </div>

        {participants.length > 0 && participants.every((p: any) => p.pct_of_issued == null) && (
          <p className="text-xs text-slate-500 mb-3">{t('pctNotDisclosed')}</p>
        )}

        {loading ? (
          <div className="text-center py-8 text-slate-400">{t('loading')}</div>
        ) : (
          <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b">
                  <th className="py-2">{t('seat')}</th>
                  <th className="py-2 text-right">{t('holdings')}</th>
                  <th className="py-2 text-right">{t('pct')}</th>
                  <th className="py-2 text-right">{t('dailyChange')}</th>
                  <th className="py-2 text-right">{t('change3d')}</th>
                  <th className="py-2">{t('attribution')}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 200).map((p: any) => (
                  <tr key={p.participant_id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-2">
                      <div className="font-medium text-slate-800 text-xs">{brokerName(p.participant_id, p.participant_name)}</div>
                      <div className="text-xs text-slate-400 font-mono">{p.participant_id}</div>
                    </td>
                    <td className="py-2 text-right font-mono text-xs">{formatShares(p.shares)}</td>
                    <td className="py-2 text-right text-xs">{p.pct_of_issued != null ? `${Number(p.pct_of_issued).toFixed(2)}%` : '—'}</td>
                    <td className={`py-2 text-right font-mono text-xs ${
                      (p.shares_change || 0) < 0 ? 'text-green-600' : (p.shares_change || 0) > 0 ? 'text-red-600' : 'text-slate-400'
                    }`}>
                      {p.shares_change != null ? (p.shares_change > 0 ? '+' : '') + formatShares(p.shares_change) : '-'}
                    </td>
                    <td className={`py-2 text-right font-mono text-xs ${
                      (p.shares_change_3d || 0) < 0 ? 'text-green-600' : (p.shares_change_3d || 0) > 0 ? 'text-red-600' : 'text-slate-400'
                    }`}>
                      {p.shares_change_3d != null ? (p.shares_change_3d > 0 ? '+' : '') + formatShares(p.shares_change_3d) : '-'}
                    </td>
                    <td className="py-2">
                      {p.shareholder_name ? (
                        <span className="badge badge-blue">{p.shareholder_name}</span>
                      ) : (
                        <span className="text-slate-300 text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
