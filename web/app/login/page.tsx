'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

const DEV_USERS = [
  { id: '447440b7-f12e-454b-8b48-7cafb60f270f', name: 'Marcus Thompson' },
  { id: '3a44403d-92d9-4afe-a88c-0daed12d8fb6', name: 'Sarah Chen' },
  { id: '926432ae-306f-48d9-9749-3b0e558f15e2', name: 'Alex Rivera' },
  { id: '8ae0c49f-4ba0-454c-991d-bbbe354b72a7', name: 'Jordan Kim' },
]

export default function LoginPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)

  function login(userId: string) {
    setLoading(true)
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
        {DEV_USERS.map(user => (
          <button
            key={user.id}
            onClick={() => login(user.id)}
            disabled={loading}
            className="w-full bg-white border border-gray-200 rounded-2xl p-4 text-left hover:border-indigo-300 hover:bg-indigo-50 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold">
                {user.name[0]}
              </div>
              <div>
                <p className="font-semibold text-gray-900">{user.name}</p>
                <p className="text-xs text-gray-400 font-mono">{user.id.slice(0, 8)}…</p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
