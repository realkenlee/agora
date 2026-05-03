import { clsx, type ClassValue } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function formatPrice(amount: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(amount)
}

export function formatRelativeTime(date: string) {
  const diff = Date.now() - new Date(date).getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}

export const CONDITION_LABELS: Record<string, string> = {
  new:      'New',
  like_new: 'Like New',
  good:     'Good',
  fair:     'Fair',
  poor:     'Poor',
}

export const CONDITION_COLORS: Record<string, string> = {
  new:      'bg-emerald-100 text-emerald-800',
  like_new: 'bg-green-100 text-green-800',
  good:     'bg-blue-100 text-blue-800',
  fair:     'bg-yellow-100 text-yellow-800',
  poor:     'bg-red-100 text-red-800',
}
