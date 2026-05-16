'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, useEffect } from 'react'
import { LayoutDashboard, Search, LogIn } from 'lucide-react'
import { cn } from '@/lib/utils'

export default function BottomNav() {
  const path = usePathname()
  const [loggedIn, setLoggedIn] = useState(false)

  useEffect(() => {
    setLoggedIn(!!localStorage.getItem('agora_token'))
  }, [path])

  const NAV = [
    { href: '/browse',    label: 'Browse',    icon: Search },
    loggedIn
      ? { href: '/dashboard', label: 'Yours', icon: LayoutDashboard }
      : { href: '/login',     label: 'Login', icon: LogIn },
  ]

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 md:hidden z-50">
      <div className="flex items-center justify-around h-16 px-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = path === href || (href === '/browse' && path === '/')
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex flex-col items-center gap-0.5 flex-1 py-2 rounded-xl transition-colors',
                active ? 'text-indigo-600' : 'text-gray-400'
              )}
            >
              <Icon size={20} strokeWidth={active ? 2 : 1.5} />
              <span className="text-xs font-medium">{label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
