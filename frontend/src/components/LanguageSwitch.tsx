import { useT } from '../lib/i18n'

export default function LanguageSwitch() {
  const { lang, setLang } = useT()

  return (
    <button
      onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
      className="bg-white/90 backdrop-blur border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-600 hover:text-slate-800 hover:shadow transition-all"
      title={lang === 'zh' ? 'Switch to English' : '切换到中文'}
    >
      🌐 {lang === 'zh' ? 'EN' : '中文'}
    </button>
  )
}
