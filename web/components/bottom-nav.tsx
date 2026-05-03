'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Home, PlusCircle, LayoutDashboard, Search, Bot } from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV = [
  { href: '/',          label: 'Home',    icon: Home },
  { href: '/browse',    label: 'Browse',  icon: Search },
  { href: '/sell',      label: 'Sell',    icon: PlusCircle, primary: true },
  { href: '/dashboard', label: 'Yours',   icon: LayoutDashboard },
  { href: '/agent',     label: 'Agent',   icon: Bot },
]

export default function BottomNav() {
  const path = usePathname()

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 md:hidden z-50">
      <div className="flex items-center justify-around h-16 px-2">
        {NAV.map(({ href, label, icon: Icon, primary }) => {
          const active = path === href
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'flex flex-col items-center gap-0.5 flex-1 py-2 rounded-xl transition-colors',
                primary
                  ? 'text-white bg-indigo-600 mx-2 py-3 rounded-2xl shadow-lg shadow-indigo-200'
                  : active
                  ? 'text-indigo-600'
                  : 'text-gray-400'
              )}
            >
              <Icon size={primary ? 24 : 20} strokeWidth={primary ? 2.5 : active ? 2 : 1.5} />
              <span className={cn('text-xs font-medium', primary && 'hidden')}>{label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
