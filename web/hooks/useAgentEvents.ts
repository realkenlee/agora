'use client'

import { useEffect, useRef } from 'react'

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://agora-production-fb42.up.railway.app'

export type AgentEventMap = {
  draft_ready?:     (data: { draft_id: string; title: string; suggested_price: number; condition: string; category_id: string }) => void
  draft_failed?:    (data: { draft_id: string; error: string }) => void
  offer_received?:  (data: { offer_id: string; listing_id: string; listing_title: string; amount: number; asking_price: number; offer_pct: number; from: string; message: string | null }) => void
  offer_accepted?:  (data: { offer_id: string; listing_id: string; amount: number }) => void
  offer_rejected?:  (data: { offer_id: string; listing_id: string }) => void
  offer_countered?: (data: { offer_id: string; listing_id: string; counter_amount: number }) => void
  message_received?: (data: { listing_id: string; listing_title: string; from: string; preview: string }) => void
  listing_live?:    (data: { listing_id: string; title: string }) => void
}

export function useAgentEvents(handlers: AgentEventMap) {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  useEffect(() => {
    const token = localStorage.getItem('agora_token')
    if (!token) return

    let es: EventSource
    let retryTimer: ReturnType<typeof setTimeout>
    let closed = false

    function connect() {
      es = new EventSource(`${BASE}/events?token=${token}`)

      const eventNames = Object.keys(handlersRef.current) as (keyof AgentEventMap)[]
      for (const name of eventNames) {
        es.addEventListener(name, (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data)
            handlersRef.current[name]?.(data as never)
          } catch { /* ignore parse errors */ }
        })
      }

      es.onerror = () => {
        es.close()
        if (!closed) {
          retryTimer = setTimeout(connect, 3000)
        }
      }
    }

    connect()

    return () => {
      closed = true
      clearTimeout(retryTimer)
      es?.close()
    }
  }, []) // intentionally empty — handlers stay current via ref
}
