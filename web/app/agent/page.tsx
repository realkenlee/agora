'use client'

import { useState } from 'react'
import { Bot, Shield, Bell, DollarSign, MessageSquare, ChevronDown, Copy, Check } from 'lucide-react'

const MCP_CONFIG = `{
  "mcpServers": {
    "agora": {
      "command": "python",
      "args": ["/path/to/agora/agent/mcp_server.py"],
      "env": {
        "AGORA_API_URL": "https://api.agora.market",
        "AGORA_API_KEY": "YOUR_KEY_HERE"
      }
    }
  }
}`

export default function AgentSetupPage() {
  const [minPricePct, setMinPricePct] = useState(80)
  const [autoRespond, setAutoRespond] = useState(true)
  const [autoRelist, setAutoRelist]   = useState(true)
  const [relistDays, setRelistDays]   = useState(7)
  const [style, setStyle]             = useState<'friendly' | 'brief' | 'formal'>('friendly')
  const [copied, setCopied]           = useState(false)
  const [saved, setSaved]             = useState(false)

  function copyConfig() {
    navigator.clipboard.writeText(MCP_CONFIG)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function save() {
    // TODO: POST to /me/agent-rules
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-100 px-4 pt-12 pb-5">
        <div className="max-w-lg mx-auto">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center">
              <Bot size={22} className="text-indigo-600" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Agent settings</h1>
          </div>
          <p className="text-sm text-gray-500 ml-13">Configure what your agent is allowed to do</p>
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-5 space-y-4">

        {/* Min price */}
        <Section icon={<DollarSign size={18} className="text-indigo-600" />} title="Minimum price">
          <p className="text-sm text-gray-500 mb-4">
            Agent will never accept or counter below this percentage of your asking price.
          </p>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={50} max={100} value={minPricePct}
              onChange={e => setMinPricePct(parseInt(e.target.value))}
              className="flex-1 accent-indigo-600"
            />
            <div className="w-16 bg-indigo-50 text-indigo-700 font-bold text-center py-2 rounded-xl text-sm">
              {minPricePct}%
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            If you list at $100, agent floor = ${Math.round(100 * minPricePct / 100)}
          </p>
        </Section>

        {/* Auto respond */}
        <Section icon={<MessageSquare size={18} className="text-indigo-600" />} title="Auto-respond to buyers">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-500">Agent answers common questions automatically</p>
            <Toggle value={autoRespond} onChange={setAutoRespond} />
          </div>
          {autoRespond && (
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-2">Response style</p>
              <div className="flex gap-2">
                {(['friendly', 'brief', 'formal'] as const).map(s => (
                  <button
                    key={s}
                    onClick={() => setStyle(s)}
                    className={`flex-1 py-2 rounded-xl text-sm font-medium capitalize transition-colors ${style === s ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-600'}`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Section>

        {/* Auto relist */}
        <Section icon={<Bell size={18} className="text-indigo-600" />} title="Auto-relist stale items">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm text-gray-500">Bump and slightly adjust price after inactivity</p>
            <Toggle value={autoRelist} onChange={setAutoRelist} />
          </div>
          {autoRelist && (
            <div className="flex items-center gap-3">
              <p className="text-sm text-gray-600">Relist after</p>
              <div className="relative">
                <select
                  value={relistDays}
                  onChange={e => setRelistDays(parseInt(e.target.value))}
                  className="appearance-none bg-gray-100 text-gray-700 font-medium pl-3 pr-8 py-1.5 rounded-lg text-sm focus:outline-none"
                >
                  {[3, 5, 7, 14, 30].map(d => <option key={d} value={d}>{d} days</option>)}
                </select>
                <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
              </div>
              <p className="text-sm text-gray-600">with no views</p>
            </div>
          )}
        </Section>

        {/* Notification */}
        <Section icon={<Bell size={18} className="text-indigo-600" />} title="Notifications">
          <div className="space-y-3">
            {[
              { label: 'New offer received', checked: true },
              { label: 'Buyer message', checked: true },
              { label: 'Listing about to expire', checked: true },
              { label: 'Item sold', checked: true },
            ].map(item => (
              <label key={item.label} className="flex items-center justify-between">
                <span className="text-sm text-gray-600">{item.label}</span>
                <input type="checkbox" defaultChecked={item.checked} className="accent-indigo-600 w-4 h-4" />
              </label>
            ))}
          </div>
        </Section>

        {/* Save */}
        <button
          onClick={save}
          className="w-full bg-indigo-600 text-white font-semibold py-4 rounded-2xl text-base"
        >
          {saved ? '✓ Saved!' : 'Save agent rules'}
        </button>

        {/* BYOA / MCP */}
        <Section icon={<Shield size={18} className="text-gray-600" />} title="Bring Your Own Agent (BYOA)">
          <p className="text-sm text-gray-500 mb-4">
            Already have Claude? Connect it via MCP. Your API key, your cost — just pay the 2% transaction fee.
          </p>
          <div className="bg-gray-900 rounded-xl p-4 relative">
            <pre className="text-green-400 text-xs overflow-x-auto no-scrollbar leading-relaxed">
              {MCP_CONFIG}
            </pre>
            <button
              onClick={copyConfig}
              className="absolute top-3 right-3 bg-gray-700 hover:bg-gray-600 text-white rounded-lg p-1.5 transition-colors"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Add this to your Claude Desktop or Claude Code config. Get your API key from the dashboard.
          </p>
        </Section>

      </div>
    </div>
  )
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-5 space-y-1">
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h2 className="font-semibold text-gray-900">{title}</h2>
      </div>
      {children}
    </div>
  )
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={`w-12 h-6 rounded-full transition-colors relative ${value ? 'bg-indigo-600' : 'bg-gray-200'}`}
    >
      <span className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${value ? 'translate-x-7' : 'translate-x-1'}`} />
    </button>
  )
}
