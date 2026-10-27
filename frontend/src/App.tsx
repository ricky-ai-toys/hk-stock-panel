import { useState, useEffect } from 'react'
import { api } from './lib/api'
import { I18nProvider, useT } from './lib/i18n'
import HomePage from './pages/HomePage'
import StockDashboard from './pages/StockDashboard'
import SettingsPage from './pages/SettingsPage'
import LanguageSwitch from './components/LanguageSwitch'

function AppInner() {
  const { t } = useT()
  const [currentStock, setCurrentStock] = useState<string | null>(null)
  const [pendingJobId, setPendingJobId] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [stocks, setStocks] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const openStock = (code: string, jobId?: string) => {
    setPendingJobId(jobId || null)
    setCurrentStock(code)
  }

  const loadStocks = async () => {
    try {
      const data = await api.listStocks()
      setStocks(data.stocks || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadStocks() }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-screen text-slate-500">{t('loading')}</div>
  }

  if (showSettings) {
    return <SettingsPage onBack={() => setShowSettings(false)} />
  }

  if (currentStock) {
    return (
      <StockDashboard
        key={currentStock}
        stockCode={currentStock}
        initialJobId={pendingJobId}
        onBack={() => { setPendingJobId(null); setCurrentStock(null); loadStocks() }}
        onStockUpdated={loadStocks}
      />
    )
  }

  return (
    <div>
      <div className="fixed top-4 right-4 z-50 flex gap-2">
        <LanguageSwitch />
        <button
          onClick={() => setShowSettings(true)}
          className="bg-white/90 backdrop-blur border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-600 hover:text-slate-800 hover:shadow transition-all"
        >
          {t('settings')}
        </button>
      </div>
      <HomePage stocks={stocks} onSelectStock={openStock} onStocksChange={loadStocks} />
    </div>
  )
}

export default function App() {
  return (
    <I18nProvider>
      <AppInner />
    </I18nProvider>
  )
}
