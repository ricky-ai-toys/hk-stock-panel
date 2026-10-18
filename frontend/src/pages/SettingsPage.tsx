import { useState, useEffect, useRef } from 'react'
import { useT } from '../lib/i18n'

interface Props {
  onBack: () => void
}

export default function SettingsPage({ onBack }: Props) {
  const { t, lang } = useT()
  const [config, setConfig] = useState<any>(null)
  const [kbDocs, setKbDocs] = useState<any[]>([])
  const [afStatus, setAfStatus] = useState<any>(null)
  const [runNowWorking, setRunNowWorking] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch('/api/config').then(r => r.json()).then(setConfig)
    loadKbDocs()
    loadAfStatus()
    const iv = setInterval(loadAfStatus, 30000)
    return () => clearInterval(iv)
  }, [])

  const loadAfStatus = async () => {
    try {
      const r = await fetch('/api/auto-fetch/status')
      setAfStatus(await r.json())
    } catch (e) { /* ignore */ }
  }

  const loadKbDocs = async () => {
    try {
      const r = await fetch('/api/knowledge/documents')
      const d = await r.json()
      setKbDocs(d.documents || [])
    } catch(e) { setKbDocs([]) }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      loadAfStatus()
    } catch (e) {
      alert(t('saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleRunNow = async () => {
    setRunNowWorking(true)
    try {
      await fetch('/api/auto-fetch/run-now', { method: 'POST' })
      setTimeout(loadAfStatus, 1500)
    } finally {
      setTimeout(() => setRunNowWorking(false), 1500)
    }
  }

  const updateField = (section: string, field: string, value: any) => {
    setConfig((prev: any) => ({
      ...prev,
      [section]: { ...prev[section], [field]: value }
    }))
  }

  if (!config) return <div className="p-8 text-center text-slate-400">{t('loading')}</div>

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={onBack} className="text-slate-500 hover:text-slate-800">{t('back')}</button>
            <h1 className="text-xl font-bold text-slate-800">{t('settingsTitle')}</h1>
          </div>
          <button onClick={handleSave} disabled={saving} className="btn btn-primary text-sm">
            {saving ? t('saving') : saved ? t('saved') : t('save')}
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <div className="card bg-blue-50 border-blue-200">
          <h3 className="font-semibold text-blue-800 mb-2">{t('outOfBox')}</h3>
          <p className="text-sm text-blue-700" dangerouslySetInnerHTML={{ __html: t('outOfBoxDesc') }} />
        </div>

        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-4">{t('servicePort')}</h3>
          <div className="space-y-3">
            <div>
              <label className="text-sm text-slate-600 block mb-1">{t('listenPort')}</label>
              <input
                type="number"
                value={config.port || 3003}
                onChange={e => setConfig({ ...config, port: parseInt(e.target.value) })}
                className="w-32 px-3 py-2 border border-slate-300 rounded-md text-sm"
              />
              <p className="text-xs text-slate-400 mt-1">{t('portRestart', { port: config.port })}</p>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold text-slate-800">{t('autoFetch')}</h3>
              <p className="text-sm text-slate-500 mt-1">{t('autoFetchDesc')}</p>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.auto_fetch?.enabled || false}
                onChange={e => updateField('auto_fetch', 'enabled', e.target.checked)}
                className="w-5 h-5"
              />
              <span className="text-sm">{t('enable')}</span>
            </label>
          </div>

          { /* Always show time/days fields so users see them before enabling */ }
          <div className="space-y-4 p-4 bg-slate-50 rounded-lg mt-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-sm text-slate-600 block mb-1">{t('autoFetchTime')}</label>
                <input
                  type="time"
                  disabled={!config.auto_fetch?.enabled}
                  value={config.auto_fetch?.time || '17:30'}
                  onChange={e => updateField('auto_fetch', 'time', e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm disabled:opacity-60"
                />
                <p className="text-xs text-slate-400 mt-1">{t('autoFetchTimeHint')}</p>
              </div>
              <div>
                <label className="text-sm text-slate-600 block mb-1">{t('autoFetchDays')}</label>
                <input
                  type="number"
                  min={7}
                  max={365}
                  disabled={!config.auto_fetch?.enabled}
                  value={config.auto_fetch?.days || 90}
                  onChange={e => updateField('auto_fetch', 'days', parseInt(e.target.value) || 90)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm disabled:opacity-60"
                />
                <p className="text-xs text-slate-400 mt-1">{t('autoFetchDaysHint')}</p>
              </div>
            </div>

            {config.auto_fetch?.enabled && (
              <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-slate-200">
                <button
                  onClick={handleRunNow}
                  disabled={runNowWorking}
                  className="btn btn-secondary text-sm disabled:opacity-50"
                >
                  {runNowWorking ? t('autoFetchRunning') : t('autoFetchRunNow')}
                </button>
                <div className="text-xs text-slate-500 space-y-0.5">
                  <div>{t('autoFetchLastRun')}: {afStatus?.last_run_date || t('autoFetchNever')}</div>
                  <div>
                    {t('autoFetchNextRun')}:{' '}
                    {afStatus?.enabled && afStatus?.next_run_in_minutes != null
                      ? (lang === 'en' ? `in ~${afStatus.next_run_in_minutes} min` : `约 ${afStatus.next_run_in_minutes} 分钟后`)
                      : '—'}
                  </div>
                </div>
              </div>
            )}
            <p className="text-xs text-slate-400 pt-1">
              {config.auto_fetch?.enabled ? t('autoFetchRunNowHint') : t('autoFetchDisabledHint')}
            </p>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold text-slate-800">{t('aiReport')}</h3>
              <p className="text-sm text-slate-500 mt-1">{t('aiReportDesc')}</p>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.llm?.enabled || false}
                onChange={e => updateField('llm', 'enabled', e.target.checked)}
                className="w-5 h-5"
              />
              <span className="text-sm">{t('enable')}</span>
            </label>
          </div>
          {config.llm?.enabled && (
            <div className="space-y-3 p-4 bg-slate-50 rounded-lg">
              <div>
                <label className="text-sm text-slate-600 block mb-1">{t('apiProvider')}</label>
                <select
                  value={config.llm?.provider || 'openai'}
                  onChange={e => updateField('llm', 'provider', e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm"
                >
                  <option value="openai">{t('provider_openai')}</option>
                  <option value="anthropic">{t('provider_anthropic')}</option>
                  <option value="deepseek">{t('provider_deepseek')}</option>
                  <option value="custom">{t('provider_custom')}</option>
                </select>
              </div>
              <div>
                <label className="text-sm text-slate-600 block mb-1">{t('apiBaseUrl')}</label>
                <input
                  type="text"
                  value={config.llm?.base_url || ''}
                  onChange={e => updateField('llm', 'base_url', e.target.value)}
                  placeholder="https://api.openai.com/v1"
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm font-mono"
                />
              </div>
              <div>
                <label className="text-sm text-slate-600 block mb-1">{t('apiKey')}</label>
                <input
                  type="password"
                  value={config.llm?.api_key === '****' ? '' : (config.llm?.api_key || '')}
                  onChange={e => updateField('llm', 'api_key', e.target.value)}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm font-mono"
                />
                <p className="text-xs text-slate-400 mt-1">{t('apiKeyLocal')}</p>
              </div>
              <div>
                <label className="text-sm text-slate-600 block mb-1">{t('modelName')}</label>
                <input
                  type="text"
                  value={config.llm?.model || ''}
                  onChange={e => updateField('llm', 'model', e.target.value)}
                  placeholder="gpt-4o-mini"
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm font-mono"
                />
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-semibold text-slate-800">{t('notifications')}</h3>
              <p className="text-sm text-slate-500 mt-1">{t('notificationsDesc')}</p>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.notification?.enabled || false}
                onChange={e => updateField('notification', 'enabled', e.target.checked)}
                className="w-5 h-5"
              />
              <span className="text-sm">{t('enable')}</span>
            </label>
          </div>
          {config.notification?.enabled && (
            <div className="space-y-3 p-4 bg-slate-50 rounded-lg">
              <div>
                <label className="text-sm text-slate-600 block mb-1">{t('webhookUrl')}</label>
                <input
                  type="text"
                  value={config.notification?.webhook_url === '****' ? '' : (config.notification?.webhook_url || '')}
                  onChange={e => updateField('notification', 'webhook_url', e.target.value)}
                  placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm font-mono"
                />
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-4">{t('companyInfo')}</h3>
          <p className="text-sm text-slate-500 mb-4">{t('companyInfoDesc')}</p>
          <div className="space-y-3">
            <div>
              <label className="text-sm text-slate-600 block mb-1">{t('companyName')}</label>
              <input
                type="text"
                value={config.company?.name || ''}
                onChange={e => updateField('company', 'name', e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm"
              />
            </div>
            <div>
              <label className="text-sm text-slate-600 block mb-1">{t('irEmail')}</label>
              <input
                type="email"
                value={config.company?.ir_email || ''}
                onChange={e => updateField('company', 'ir_email', e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm"
              />
            </div>
            <div>
              <label className="text-sm text-slate-600 block mb-1">{t('logoUrl')}</label>
              <input
                type="text"
                value={config.company?.logo_url || ''}
                onChange={e => updateField('company', 'logo_url', e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm font-mono"
              />
            </div>
          </div>
        </div>

        {/* Knowledge Base */}
        <div className="card">
          <h3 className="font-semibold text-slate-800 mb-2">📚 {lang === 'en' ? 'AI Knowledge Base (RAG)' : 'AI知识库（RAG）'}</h3>
          <p className="text-sm text-slate-500 mb-4">
            {lang === 'en'
              ? 'Upload reference reports or paste analysis rules. AI-enhanced reports will follow these rules and styles.'
              : '上传参考报告或粘贴分析规则。AI增强报告将遵循这些规则和风格。内置方法论已包含，不可删除。'}
          </p>

          {/* Built-in docs indicator */}
          <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-800 font-medium">
              {lang === 'en' ? '✅ Built-in (4 docs): CCASS Methodology · Writing Style · Cost Framework · Capital Flow Framework' : '✅ 内置文档（4篇）：CCASS方法论 · 写作规范 · 成本分析框架 · 资金流向框架'}
            </p>
          </div>

          {/* Existing custom docs list */}
          {kbDocs.filter(d => d.name.startsWith('custom_')).length > 0 && (
            <div className="mb-4">
              <p className="text-sm font-medium text-slate-700 mb-2">{lang === 'en' ? 'Custom Documents' : '自定义文档'}</p>
              <div className="space-y-2">
                {kbDocs.filter(d => d.name.startsWith('custom_')).map(d => (
                  <div key={d.name} className="flex items-center justify-between p-2 bg-slate-50 rounded border border-slate-200">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-700 truncate">{d.name.replace('custom_','')}</p>
                      <p className="text-xs text-slate-400">{d.chars} chars · {d.modified}</p>
                    </div>
                    <button
                      onClick={async () => {
                        await fetch(`/api/knowledge/documents/${encodeURIComponent(d.name)}`, { method: 'DELETE' })
                        loadKbDocs()
                      }}
                      className="ml-2 text-red-500 hover:text-red-700 text-sm"
                    >
                      🗑️
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Add new document */}
          <KbAddForm lang={lang} onAdded={loadKbDocs} />
        </div>

        <div className="text-center text-xs text-slate-400 py-4">
          <p dangerouslySetInnerHTML={{ __html: t('configFileLocation') }} />
          <p className="mt-1">{t('allDataLocal')}</p>
        </div>
      </main>
    </div>
  )
}

function KbAddForm({ lang, onAdded }: { lang: string; onAdded: () => void }) {
  const [docName, setDocName] = useState('')
  const [docContent, setDocContent] = useState('')
  const [adding, setAdding] = useState(false)

  const handleAdd = async () => {
    if (!docName.trim() || !docContent.trim()) return
    setAdding(true)
    try {
      await fetch('/api/knowledge/documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: docName.trim(), content: docContent, category: 'custom' })
      })
      setDocName('')
      setDocContent('')
      onAdded()
    } finally {
      setAdding(false)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const text = await file.text()
    setDocName(file.name.replace(/\.[^.]+$/, ''))
    setDocContent(text)
  }

  return (
    <div className="border-t border-slate-200 pt-4">
      <p className="text-sm font-medium text-slate-700 mb-2">
        {lang === 'en' ? 'Add New Rule / Document' : '添加新规则 / 文档'}
      </p>
      <div className="space-y-2">
        <input
          type="text"
          value={docName}
          onChange={e => setDocName(e.target.value)}
          placeholder={lang === 'en' ? 'Rule name, e.g. "My analysis style", "Key signals I look for"' : '规则名称，如"我的分析风格"、"我关注的关键信号"'}
          className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm"
        />
        <textarea
          value={docContent}
          onChange={e => setDocContent(e.target.value)}
          rows={8}
          placeholder={
            lang === 'en'
              ? 'Write your analysis rules here, e.g.:\n\n## My Analysis Rules\n- Always check if CCASS inflow is from dematerialization vs new buying\n- A single broker change >1% of shares is high priority\n- Compare southbound flow direction with price action\n- ...any custom rules, style preferences, or reference frameworks...'
              : '在这里写你的分析规则，例如：\n\n## 我的分析规则\n- 始终区分CCASS净流入是电子化转入还是新资金买入\n- 单一席位单日变动>1%总股本为高优先级\n- 南向资金方向要与价格走势对比\n- ...任何自定义规则、风格偏好或参考框架...'
          }
          className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm font-mono"
        />
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={handleAdd} disabled={adding || !docName.trim() || !docContent.trim()} className="btn btn-primary text-sm disabled:opacity-50">
            {adding ? (lang === 'en' ? 'Adding...' : '添加中...') : (lang === 'en' ? 'Add Rule' : '添加规则')}
          </button>
          <label className="btn btn-secondary text-sm cursor-pointer">
            📁 {lang === 'en' ? 'Upload File' : '上传文件'}
            <input type="file" accept=".txt,.md,.html,.csv" className="hidden" onChange={handleFileUpload} />
          </label>
          <span className="text-xs text-slate-400">
            {lang === 'en' ? 'Supports .txt, .md, .html, .csv' : '支持 .txt, .md, .html, .csv 文件'}
          </span>
        </div>
      </div>
    </div>
  )
}
