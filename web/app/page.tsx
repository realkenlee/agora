import Link from 'next/link'
import { Camera, Bot, Bell, ArrowRight, Zap, ShieldCheck, Cpu } from 'lucide-react'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white">

      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-4xl mx-auto">
        <span className="text-xl font-bold text-gray-900 tracking-tight">agora</span>
        <div className="flex items-center gap-4">
          <Link href="/browse" className="text-sm text-gray-500 hover:text-gray-900 hidden md:block">Browse</Link>
          <Link href="/dashboard" className="text-sm text-gray-500 hover:text-gray-900 hidden md:block">Dashboard</Link>
          <Link href="/sell" className="bg-indigo-600 text-white text-sm font-semibold px-4 py-2 rounded-xl hover:bg-indigo-700 transition-colors">
            Start selling
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
          Point.<br />Shoot.<br /><span className="text-indigo-600">Sold.</span>
        </h1>
        <p className="text-lg text-gray-500 mb-8 max-w-md mx-auto leading-relaxed">
          Take a photo of anything you want to sell. Your agent writes the listing,
          handles every buyer question, and texts you when it&apos;s time to confirm.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link href="/sell" className="bg-indigo-600 text-white font-semibold px-8 py-4 rounded-2xl text-lg flex items-center justify-center gap-2 hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-200">
            <Camera size={22} />
            Sell something now
          </Link>
          <Link href="/browse" className="border border-gray-200 text-gray-700 font-semibold px-8 py-4 rounded-2xl text-lg flex items-center justify-center gap-2 hover:border-gray-300 transition-colors">
            Browse listings <ArrowRight size={20} />
          </Link>
        </div>
      </section>

      {/* How it works */}
      <section className="px-6 py-16 bg-gray-50">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-bold text-gray-900 text-center mb-10">You touch it twice</h2>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              { icon: <Camera size={28} className="text-indigo-600" />, step: '1', title: 'Take a photo', body: 'Point your phone. One sentence. Agent writes the title, description, and suggests the right price.' },
              { icon: <Bot size={28} className="text-indigo-600" />, step: '2', title: 'Agent handles everything', body: 'Answers buyer questions, negotiates within your rules, relists if it goes stale. Zero effort from you.' },
              { icon: <Bell size={28} className="text-indigo-600" />, step: '3', title: 'You get a notification', body: '"You have a buyer for $180. Confirm?" One tap. Done. The agent schedules the meetup.' },
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

      {/* Pricing */}
      <section className="px-6 py-16 max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold text-gray-900 text-center mb-2">Simple pricing</h2>
        <p className="text-gray-500 text-center mb-10">The marketplace is free. Pay only for the agent.</p>
        <div className="grid md:grid-cols-3 gap-4">
          {[
            { name: 'Free', price: '$0', sub: '+ 3% on sales', features: ['List items manually', 'Browse and buy', 'Basic messaging', 'Up to 10 listings'], cta: null, highlight: false },
            { name: 'Agent Pro', price: '$20', sub: '+ 2% on sales', features: ['We run Claude for you', 'Photo → listed in seconds', 'Agent responds to buyers', 'Agent negotiates for you', 'Notify to confirm sale', 'Unlimited listings'], cta: { label: 'Start free trial', href: '/sell' }, highlight: true },
            { name: 'BYOA', price: '$0', sub: '+ 2% on sales', features: ['Bring your own Claude', 'Connect via MCP', 'Your API key, your cost', 'Full API access', 'Unlimited listings'], cta: { label: 'View MCP docs', href: '/docs/mcp' }, highlight: false },
          ].map(({ name, price, sub, features, cta, highlight }) => (
            <div key={name} className={`rounded-2xl p-6 space-y-4 relative ${highlight ? 'border-2 border-indigo-600' : 'border border-gray-200'}`}>
              {highlight && <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-xs font-bold px-3 py-1 rounded-full">Most popular</div>}
              <div>
                <p className="font-bold text-gray-900 flex items-center gap-1.5">
                  {name === 'Agent Pro' && <Bot size={15} className="text-indigo-600" />}
                  {name === 'BYOA' && <Cpu size={15} className="text-gray-500" />}
                  {name}
                </p>
                <p className="text-3xl font-extrabold text-gray-900 mt-1">{price}<span className="text-base font-medium text-gray-400">{name !== 'Free' ? '/mo' : ''}</span></p>
                <p className="text-xs text-gray-400 mt-0.5">{sub}</p>
              </div>
              <ul className="space-y-2 text-sm text-gray-600">
                {features.map(f => (
                  <li key={f} className="flex items-start gap-2">
                    <span className={highlight ? 'text-indigo-500' : 'text-gray-300'}>✓</span> {f}
                  </li>
                ))}
              </ul>
              {cta && (
                <Link href={cta.href} className={`block w-full font-semibold py-3 rounded-xl text-center text-sm transition-colors ${highlight ? 'bg-indigo-600 text-white hover:bg-indigo-700' : 'border border-gray-200 text-gray-700 hover:border-gray-300'}`}>
                  {cta.label}
                </Link>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Trust bar */}
      <section className="px-6 py-12 bg-gray-50 border-t border-gray-100">
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
