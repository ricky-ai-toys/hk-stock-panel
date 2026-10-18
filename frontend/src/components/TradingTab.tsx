import { useState, useEffect } from 'react'
import { api, formatShares, formatMoney } from '../lib/api'
import { useT } from '../lib/i18n'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceDot } from 'recharts'

export default function TradingTab({ stockCode }: { stockCode: string }) {
  const [data, setData] = useState<any[]>([])
  const [announcements, setAnnouncements] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchingAnn, setFetchingAnn] = useState(false)
  const { t } = useT()

  const load = async () => {
    setLoading(true)
    try {
      const [trading, annRes] = await Promise.all([
        api.getTrading(stockCode, 180),
        api._get(`/stock/${stockCode}/announcements?days=180`).catch(() => ({ announcements: [] })),
      ])
      setData(trading)
      setAnnouncements(annRes.announcements || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [stockCode])

  const handleFetchAnnouncements = async () => {
    setFetchingAnn(true)
    try {
      const result = await api._post(`/stock/${stockCode}/announcements/fetch?days=180`)
      if (result.job_id) {
        const poll = setInterval(async () => {
          try {
            const status = await api._get(`/jobs/${result.job_id}`)
            if (status.status === 'done' || status.status === 'error') {
              clearInterval(poll)
              setFetchingAnn(false)
              const annRes = await api._get(`/stock/${stockCode}/announcements?days=180`)
              setAnnouncements(annRes.announcements || [])
            }
          } catch { clearInterval(poll); setFetchingAnn(false) }
        }, 3000)
      }
    } catch (e) {
      setFetchingAnn(false)
    }
  }

  const closeLabel = t('close')
  const volLabel = t('volume_short')
  const chartData = data.map((d: any) => ({
    date: d.trade_date?.slice(5),
    fullDate: d.trade_date,
    [closeLabel]: d.close,
    [volLabel]: d.volume ? d.volume / 1000000 : 0,
  }))

  // Category translation map: zh source -> translate key
  const catMap: Record<string, string> = {
    '业绩公告': 'cat_earnings',
    '回购': 'cat_buyback',
    '增减持': 'cat_trade',
    '配股/融资': 'cat_placing',
    '董事变动': 'cat_director',
    '重大事项': 'cat_material',
    '股息': 'cat_dividend',
    '其他': 'cat_other',
  }

  const translateCategory = (cat: string) => {
    const key = catMap[cat]
    return key ? t(key) : cat
  }

  // Material categories for annotation
  const materialCatsZh = ['业绩公告', '回购', '配股/融资', '增减持']

  // Map announcements to chart points
  const annPoints = announcements
    .filter((a: any) => a.is_material || materialCatsZh.includes(a.category))
    .slice(0, 15)
    .map((a: any) => {
      const matchingPoint = chartData.find((c: any) => c.fullDate === a.announce_date)
      if (!matchingPoint) return null
      return {
        x: matchingPoint.date,
        y: matchingPoint[closeLabel],
        title: a.title?.slice(0, 30) + (a.title?.length > 30 ? '...' : ''),
        category: a.category,
        categoryLabel: translateCategory(a.category),
        date: a.announce_date,
      }
    }).filter(Boolean)

  const categoryColors: Record<string, string> = {
    '业绩公告': '#2563eb',
    '回购': '#16a34a',
    '增减持': '#dc2626',
    '配股/融资': '#ea580c',
    '董事变动': '#7c3aed',
    '重大事项': '#eab308',
    '股息': '#0891b2',
    '其他': '#64748b',
  }

  return (
    <div className="space-y-6">
      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">{t('priceChart6m')}</h3>
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
            <Tooltip
              content={({ active, payload, label }) => {
                if (active && payload && payload.length) {
                  const d = payload[0].payload
                  const ann = annPoints.find((a: any) => a.x === label)
                  return (
                    <div className="bg-white border rounded-lg shadow-lg p-3 text-xs">
                      <p className="font-semibold">{d.fullDate}</p>
                      <p>{t('close')}: HK${d[closeLabel]?.toFixed(2)}</p>
                      {ann && (
                        <p className="mt-1 text-blue-600 max-w-[200px]">📢 {ann.title}</p>
                      )}
                    </div>
                  )
                }
                return null
              }}
            />
            <Line type="monotone" dataKey={closeLabel} stroke="#2563eb" strokeWidth={2} dot={false} />
            {annPoints.map((a: any, i: number) => (
              <ReferenceDot
                key={i}
                x={a.x}
                y={a.y}
                r={5}
                fill={categoryColors[a.category] || '#64748b'}
                stroke="white"
                strokeWidth={2}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
        {annPoints.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {Object.entries(categoryColors).map(([cat, color]) => {
              const count = annPoints.filter((a: any) => a.category === cat).length
              if (count === 0) return null
              return (
                <span key={cat} className="flex items-center gap-1 text-xs">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }}></span>
                  {translateCategory(cat)}({count})
                </span>
              )
            })}
          </div>
        )}
      </div>

      {/* Announcements */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-slate-800">{t('announcements')}</h3>
          <button onClick={handleFetchAnnouncements} disabled={fetchingAnn} className="btn btn-secondary text-sm">
            {fetchingAnn ? t('fetchingAnn') : t('fetchAnnouncements')}
          </button>
        </div>
        {announcements.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-sm">
            {t('noAnnouncements')}
          </div>
        ) : (
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {announcements.map((a: any, i: number) => {
              const color = categoryColors[a.category] || '#64748b'
              return (
                <div key={i} className="flex items-start gap-3 p-3 border border-slate-100 rounded-lg hover:bg-slate-50">
                  <span className="badge shrink-0" style={{ background: color + '15', color: color }}>
                    {translateCategory(a.category || '其他')}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm text-slate-800">{a.title}</p>
                    <p className="text-xs text-slate-400 mt-1">{a.announce_date}</p>
                  </div>
                  {a.pdf_url && (
                    <a href={a.pdf_url} target="_blank" rel="noopener" className="text-xs text-blue-600 shrink-0 ml-auto">
                      PDF →
                    </a>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Trading Table */}
      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">{t('tradingDetails')}</h3>
        {loading ? (
          <div className="text-center py-8 text-slate-400">{t('loading')}</div>
        ) : (
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-slate-500 border-b">
                  <th className="py-2">{t('date')}</th>
                  <th className="py-2 text-right">{t('close')}</th>
                  <th className="py-2 text-right">{t('change')}</th>
                  <th className="py-2 text-right">{t('volume_short')}</th>
                  <th className="py-2 text-right">{t('turnover')}</th>
                </tr>
              </thead>
              <tbody>
                {[...data].reverse().map((d: any) => (
                  <tr key={d.trade_date} className="border-b border-slate-100">
                    <td className="py-2 font-mono text-xs">{d.trade_date}</td>
                    <td className="py-2 text-right font-medium">{d.close?.toFixed(2)}</td>
                    <td className={`py-2 text-right font-mono text-xs ${
                      (d.change_pct || 0) >= 0 ? 'text-red-600' : 'text-green-600'
                    }`}>
                      {(d.change_pct || 0) >= 0 ? '+' : ''}{d.change_pct?.toFixed(2)}%
                    </td>
                    <td className="py-2 text-right text-xs">{formatShares(d.volume)}</td>
                    <td className="py-2 text-right text-xs">{formatMoney(d.turnover)}</td>
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
