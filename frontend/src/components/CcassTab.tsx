import { useState, useEffect } from 'react'
import { api, formatShares } from '../lib/api'
import { useT } from '../lib/i18n'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

export default function CcassTab({ stockCode }: { stockCode: string }) {
  const [participants, setParticipants] = useState<any[]>([])
  const [hkConnect, setHkConnect] = useState<any[]>([])
  const [selectedDate, setSelectedDate] = useState<string>('')
  const [dates, setDates] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState<'all' | 'changes'>('all')
  const [exporting, setExporting] = useState(false)
  const { t, brokerName } = useT()

  const load = async () => {
    setLoading(true)
    try {
      const [datesRes, pRes, cRes, hkRes] = await Promise.all([
        api.getDates(stockCode),
        api.getParticipants(stockCode, selectedDate || undefined),
        api.getChanges(stockCode, selectedDate || undefined),
        api.getHkConnect(stockCode, 90),
      ])
      setHkConnect(hkRes)
      setDates(datesRes.dates || [])

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
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [stockCode, selectedDate])

  const handleExport = () => {
    setExporting(true)
    window.open(`/api/stock/${stockCode}/export`, '_blank')
    setTimeout(() => setExporting(false), 1000)
  }

  const netBuyLabel = t('netBuy')
  const hkChartData = hkConnect.map((h: any) => ({
    date: h.trade_date?.slice(5),
    [netBuyLabel]: Math.round((h.shares_change || 0) / 10000),
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
      {/* Southbound bar chart */}
      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">{t('southboundDailyNet')}</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={hkChartData.slice(-30)}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey={netBuyLabel} fill="#8b5cf6" />
          </BarChart>
        </ResponsiveContainer>
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
