'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://agora-production-2bbb.up.railway.app'

type User = { id: string; display_name: string }

export default function LoginPage() {
  const router = useRouter()
  const [users, setUsers] = useState<User[]>([])

  useEffect(() => {
    fetch(`${BASE}/dev/users`).then(r => r.json()).then(setUsers).catch(() => {})
  }, [])

  function login(userId: string) {
    localStorage.setItem('agora_token', userId)
    router.push('/dashboard')
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4 gap-6">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-gray-900">Dev Login</h1>
        <p className="text-gray-500 text-sm mt-1">Pick a test account</p>
      </div>
      <div className="w-full max-w-sm space-y-3">
        {users.map(user => (
          <button
            key={user.id}
            onClick={() => login(user.id)}
            className="w-full bg-white border border-gray-200 rounded-2xl p-4 text-left hover:border-indigo-300 hover:bg-indigo-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold">
                {user.display_name[0]}
              </div>
              <div>
                <p className="font-semibold text-gray-900">{user.display_name}</p>
                <p className="text-xs text-gray-400 font-mono">{user.id.slice(0, 8)}…</p>
              </div>
            </div>
          </button>
        ))}
        {users.length === 0 && (
          <p className="text-center text-gray-400 text-sm">Loading…</p>
        )}
      </div>
    </div>
  )
}
