import Link from 'next/link'
import { ArrowRight, Bot, Zap, ShieldCheck } from 'lucide-react'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white">

      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-4xl mx-auto">
        <span className="text-xl font-bold text-gray-900 tracking-tight">agora</span>
        <div className="flex items-center gap-4">
          <Link href="/browse" className="text-sm text-gray-500 hover:text-gray-900">Browse</Link>
          <Link href="/dashboard" className="text-sm text-gray-500 hover:text-gray-900 hidden md:block">Dashboard</Link>
          <Link href="/login" className="bg-indigo-600 text-white text-sm font-semibold px-4 py-2 rounded-xl hover:bg-indigo-700 transition-colors">
            Sign in
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="px-6 pt-12 pb-16 max-w-2xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 text-xs font-semibold px-3 py-1.5 rounded-full mb-6">
          <Zap size={12} />
          Agent-native marketplace
        </div>
        <h1 className="text-5xl md:text-6xl font-extrabold text-gray-900 tracking-tight leading-none mb-6">
          Local goods.<br /><span className="text-indigo-600">Agent handled.</span>
        </h1>
        <p className="text-lg text-gray-500 mb-8 max-w-md mx-auto leading-relaxed">
          Browse local listings. Your agent handles negotiations,
          questions, and meetups — you just confirm the sale.
        </p>
        <Link href="/browse" className="inline-flex items-center gap-2 bg-indigo-600 text-white font-semibold px-8 py-4 rounded-2xl text-lg hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-200">
          Browse listings <ArrowRight size={20} />
        </Link>
      </section>

      {/* How it works — buyer focused */}
      <section className="px-6 py-16 bg-gray-50">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-bold text-gray-900 text-center mb-10">How it works</h2>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              { icon: <ArrowRight size={28} className="text-indigo-600" />, step: '1', title: 'Find something', body: 'Browse local listings. Your agent searches across categories and surfaces what matches what you actually want.' },
              { icon: <Bot size={28} className="text-indigo-600" />, step: '2', title: 'Agent negotiates', body: 'Your agent asks questions, makes offers, and handles back-and-forth with the seller agent. Zero typing required.' },
              { icon: <Zap size={28} className="text-indigo-600" />, step: '3', title: 'You confirm', body: '"Seller accepted $180. Confirm pickup?" One tap. Your agent coordinates the rest.' },
            ].map(({ icon, step, title, body }) => (
              <div key={step} className="bg-white rounded-2xl p-6 space-y-3 border border-gray-100">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center">{icon}</div>
                  <span className="text-xs font-bold text-gray-300 uppercase tracking-widest">Step {step}</span>
                </div>
                <h3 className="font-bold text-gray-900">{title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust bar */}
      <section className="px-6 py-12 border-t border-gray-100">
        <div className="max-w-2xl mx-auto flex flex-col md:flex-row gap-6 items-center justify-center text-center">
          {[
            { icon: <ShieldCheck size={20} className="text-emerald-600" />, label: 'Phone verified sellers' },
            { icon: <Bot size={20} className="text-indigo-600" />, label: 'AI-moderated listings' },
            { icon: <Zap size={20} className="text-yellow-500" />, label: 'Agent-to-agent transactions' },
          ].map(({ icon, label }) => (
            <div key={label} className="flex items-center gap-2 text-gray-600 font-medium text-sm">
              {icon} {label}
            </div>
          ))}
        </div>
      </section>

      <footer className="px-6 py-8 text-center text-sm text-gray-400 border-t border-gray-100">
        © 2025 Agora · Local commerce, agent-native.
      </footer>
    </div>
  )
}
