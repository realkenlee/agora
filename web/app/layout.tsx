import type { Metadata, Viewport } from 'next'
import './globals.css'
import BottomNav from '@/components/bottom-nav'

export const metadata: Metadata = {
  title: 'Agora — Point. Shoot. Sold.',
  description: 'The agent-native local marketplace. Sell anything in seconds.',
  manifest: '/manifest.json',
  appleWebApp: { capable: true, statusBarStyle: 'default', title: 'Agora' },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  themeColor: '#ffffff',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full flex flex-col bg-white text-gray-900">
        <main className="flex-1 pb-20 md:pb-0">
          {children}
        </main>
        <BottomNav />
      </body>
    </html>
  )
}
