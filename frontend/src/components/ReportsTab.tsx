import { useState } from 'react'
import { useT } from '../lib/i18n'

export default function ReportsTab({ stockCode, stockName }: { stockCode: string; stockName?: string }) {
  const { t, lang } = useT()
  const [reportType, setReportType] = useState<'daily' | 'weekly' | 'monthly'>('weekly')
  const [mode, setMode] = useState<'trader' | 'ir'>('trader')
  const [useAi, setUseAi] = useState(false)
  const [loading, setLoading] = useState(false)
  const [report, setReport] = useState<any>(null)

  const handleGenerate = async () => {
    setLoading(true)
    setReport(null)
    try {
      const aiParam = useAi ? '&use_ai=true' : ''
      const res = await fetch(`/api/stock/${stockCode}/report?report_type=${reportType}&mode=${mode}&lang=${lang}${aiParam}`)
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      setReport(data)
    } catch (e: any) {
      alert(t('generateFailed') + ': ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (!report) return
    const content = report.ai_content || report.markdown
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${report.stock_code}_${report.report_type}_${report.mode}_${new Date().toISOString().slice(0,10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleViewHtml = () => {
    if (!report) return
    const aiParam = useAi ? '&use_ai=true' : ''
    const url = `/api/stock/${stockCode}/report?report_type=${reportType}&mode=${mode}&lang=${lang}&format=html${aiParam}`
    window.open(url, '_blank')
  }

  const renderMarkdown = (md: string) => {
    if (!md) return null
    return md.split('\n').map((line: string, i: number) => {
      if (line.startsWith('# ')) return <h1 key={i} className="text-xl font-bold text-slate-800 mt-4 mb-2">{line.slice(2)}</h1>
      if (line.startsWith('## ')) return <h2 key={i} className="text-lg font-bold text-slate-800 mt-4 mb-2 border-b pb-1">{line.slice(3)}</h2>
      if (line.startsWith('- ')) {
        const content = line.slice(2)
          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
          .replace(/🔴/g, '<span class="text-red-600">🔴</span>')
          .replace(/🟢/g, '<span class="text-green-600">🟢</span>')
        return <li key={i} className="ml-4 text-sm text-slate-700 list-disc" dangerouslySetInnerHTML={{ __html: content }} />
      }
      if (line.startsWith('---')) return <hr key={i} className="my-4 border-slate-200" />
      if (!line.trim()) return <br key={i} />
      return <p key={i} className="text-sm text-slate-600" dangerouslySetInnerHTML={{
        __html: line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      }} />
    })
  }

  return (
    <div className="space-y-6">
      <div className="card">
        <h3 className="font-semibold text-slate-800 mb-4">{t('autoGenerateReport')}</h3>

        <div className="flex flex-wrap items-center gap-4 mb-4">
          <div>
            <label className="text-sm text-slate-500 block mb-1">{t('reportType')}</label>
            <div className="flex bg-slate-100 rounded-md p-0.5">
              {[
                { k: 'daily', l: t('daily') },
                { k: 'weekly', l: t('weekly') },
                { k: 'monthly', l: t('monthly') },
              ].map(v => (
                <button
                  key={v.k}
                  onClick={() => setReportType(v.k as any)}
                  className={`px-4 py-1.5 text-sm rounded transition-colors ${
                    reportType === v.k ? 'bg-white shadow text-slate-800 font-medium' : 'text-slate-500'
                  }`}
                >
                  {v.l}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-sm text-slate-500 block mb-1">{t('reportMode')}</label>
            <div className="flex bg-slate-100 rounded-md p-0.5">
              <button
                onClick={() => setMode('trader')}
                className={`px-4 py-1.5 text-sm rounded transition-colors ${
                  mode === 'trader' ? 'bg-white shadow text-slate-800 font-medium' : 'text-slate-500'
                }`}
              >
                {t('traderView')}
              </button>
              <button
                onClick={() => setMode('ir')}
                className={`px-4 py-1.5 text-sm rounded transition-colors ${
                  mode === 'ir' ? 'bg-white shadow text-slate-800 font-medium' : 'text-slate-500'
                }`}
              >
                {t('irView')}
              </button>
            </div>
          </div>

          <div>
            <label className="text-sm text-slate-500 block mb-1">AI</label>
            <div className="flex bg-slate-100 rounded-md p-0.5">
              <button
                onClick={() => setUseAi(false)}
                className={`px-4 py-1.5 text-sm rounded transition-colors ${
                  !useAi ? 'bg-white shadow text-slate-800 font-medium' : 'text-slate-500'
                }`}
              >
                {t('template')}
              </button>
              <button
                onClick={() => setUseAi(true)}
                className={`px-4 py-1.5 text-sm rounded transition-colors ${
                  useAi ? 'bg-white shadow text-slate-800 font-medium' : 'text-slate-500'
                }`}
              >
                {t('aiEnhanced')}
              </button>
            </div>
          </div>

          <div className="self-end">
            <button onClick={handleGenerate} disabled={loading} className="btn btn-primary">
              {loading ? t('generating') : t('generateReport')}
            </button>
          </div>
        </div>

        {useAi && <p className="text-xs text-amber-600 mb-2">💡 {t('aiEnhancedHint')}</p>}
        <p className="text-xs text-slate-400">
          {mode === 'ir' ? t('irModeHint') : t('traderModeHint')}
        </p>
      </div>

      {report && (
        <div className="card">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <div>
              <h3 className="font-bold text-lg text-slate-800">{report.title}</h3>
              <p className="text-sm text-slate-500">{t('reportPeriod')}: {report.date_range} · {t('generatedAt')}: {report.generated_at}</p>
            </div>
            <div className="flex gap-2">
              <button onClick={handleViewHtml} className="btn btn-secondary text-sm">{t('webVersion')}</button>
              <button onClick={handleDownload} className="btn btn-secondary text-sm">{t('downloadMd')}</button>
            </div>
          </div>
          {report.score != null && !useAi && (
            <div className="mb-4 p-3 rounded-lg text-sm" style={{
              background: report.score >= 60 ? '#fef2f2' : report.score <= 40 ? '#f0fdf4' : '#fefce8',
              color: report.score >= 60 ? '#dc2626' : report.score <= 40 ? '#16a34a' : '#ca8a04'
            }}>
              {t('signalScore')}: <strong>{report.score}/100</strong>
            </div>
          )}
          <div className="prose max-w-none">
            {renderMarkdown(report.ai_content || report.markdown)}
          </div>
        </div>
      )}
    </div>
  )
}
