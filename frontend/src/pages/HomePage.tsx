import { useState } from 'react'
import { api } from '../lib/api'
import { useT } from '../lib/i18n'

interface Props {
  stocks: any[]
  onSelectStock: (code: string, jobId?: string) => void
  onStocksChange: () => void
}

export default function HomePage({ stocks, onSelectStock, onStocksChange }: Props) {
  const { t, stockName: stockNameI18n } = useT()
  const [codeInput, setCodeInput] = useState('')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')

  const handleAddStock = async () => {
    const code = codeInput.trim().replace(/[^0-9]/g, '').padStart(5, '0')
    if (code.length !== 5 || isNaN(Number(code))) {
      setError(t('invalidCode'))
      return
    }
    setAdding(true)
    setError('')
    try {
      const added = await api.addStock(code)
      onStocksChange()
      setCodeInput('')
      onSelectStock(code, added.job_id)
    } catch (e: any) {
      setError(e.message || t('addFailed'))
    } finally {
      setAdding(false)
    }
  }

  const features = [
    { icon: '📊', title: t('feature_ccass.title'), desc: t('feature_ccass.desc') },
    { icon: '🏦', title: t('feature_southbound.title'), desc: t('feature_southbound.desc') },
    { icon: '🚨', title: t('feature_anomaly.title'), desc: t('feature_anomaly.desc') },
    { icon: '📉', title: t('feature_selloff.title'), desc: t('feature_selloff.desc') },
    { icon: '📅', title: t('feature_unlock.title'), desc: t('feature_unlock.desc') },
    { icon: '📝', title: t('feature_report.title'), desc: t('feature_report.desc') },
  ]

  const traderItems = t('traderModeDesc', { returnObjects: true }) as string[]
  const irItems = t('irModeDesc', { returnObjects: true }) as string[]

  return (
    <div className="min-h-screen">
      <header className="bg-gradient-to-br from-slate-900 via-slate-800 to-blue-900 text-white">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-4xl">📊</span>
            <h1 className="text-3xl font-bold tracking-tight">{t('appTitle')}</h1>
          </div>
          <p className="text-lg text-slate-300 mb-8 max-w-2xl">{t('heroSubtitle')}</p>

          <div className="bg-white/10 backdrop-blur rounded-xl p-6 border border-white/20 max-w-xl">
            <h2 className="text-sm font-medium text-slate-300 mb-3">{t('searchPrompt')}</h2>
            <div className="flex gap-3">
              <input
                type="text"
                value={codeInput}
                onChange={e => setCodeInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAddStock()}
                placeholder={t('addStockPlaceholder')}
                className="flex-1 px-4 py-3 rounded-lg text-lg font-mono bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                maxLength={5}
              />
              <button
                onClick={handleAddStock}
                disabled={adding}
                className="px-8 py-3 bg-blue-500 hover:bg-blue-400 rounded-lg font-semibold transition-colors disabled:opacity-50 whitespace-nowrap"
              >
                {adding ? t('loading') : t('query')}
              </button>
            </div>
            {error && <p className="text-red-300 text-sm mt-2">{error}</p>}
            {stocks.length > 0 && (
              <p className="text-slate-400 text-sm mt-3">{t('added', { count: stocks.length })}</p>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-12">
        <h2 className="text-2xl font-bold text-slate-800 mb-6">{t('features')}</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-12">
          {features.map(f => (
            <div key={f.title} className="card hover:shadow-md transition-shadow">
              <div className="text-3xl mb-3">{f.icon}</div>
              <h3 className="font-semibold text-slate-800 mb-1">{f.title}</h3>
              <p className="text-sm text-slate-500">{f.desc}</p>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
          <div className="card border-blue-200 bg-blue-50/30">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-2xl">📈</span>
              <h3 className="font-bold text-slate-800">{t('traderMode')}</h3>
            </div>
            <ul className="text-sm text-slate-600 space-y-2">
              {traderItems.map((item: string, i: number) => <li key={i}>{item}</li>)}
            </ul>
          </div>
          <div className="card border-purple-200 bg-purple-50/30">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-2xl">🏢</span>
              <h3 className="font-bold text-slate-800">{t('irMode')}</h3>
            </div>
            <ul className="text-sm text-slate-600 space-y-2">
              {irItems.map((item: string, i: number) => <li key={i}>{item}</li>)}
            </ul>
          </div>
        </div>

        {stocks.length > 0 && (
          <div>
            <h2 className="text-xl font-bold text-slate-800 mb-4">{t('myStocks')}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {stocks.map((s: any) => (
                <div
                  key={s.stock_code}
                  className="flex items-center justify-between p-4 border border-slate-200 rounded-lg hover:border-blue-400 hover:shadow cursor-pointer transition-all bg-white"
                  onClick={() => onSelectStock(s.stock_code)}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-lg font-bold text-slate-800">{s.stock_code}.HK</span>
                      <span className="text-slate-600">{stockNameI18n(s.stock_code, s.stock_name) || '—'}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                      {s.is_ir_configured ? (
                        <span className="badge badge-blue">{t('irConfigured')}</span>
                      ) : (
                        <span className="badge badge-gray">{t('publicMode')}</span>
                      )}
                      {s.last_updated && (
                        <span>{t('updatedAt')} {s.last_updated?.slice(5, 16)}</span>
                      )}
                    </div>
                  </div>
                  <span className="text-slate-400 text-xl">→</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-16 pt-8 border-t border-slate-200 text-center text-sm text-slate-400">
          <p>{t('footerPrivacy')}</p>
          <p className="mt-1">{t('footerSource')}</p>
          <p className="mt-2 text-xs">© 2026 stevenshi-vibe · CC BY-NC 4.0 · <a href="https://github.com/stevenshi-vibe/hk-stock-panel" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">hk-stock-panel</a></p>
        </div>
      </main>
    </div>
  )
}
