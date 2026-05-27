import { useEffect, useMemo, useRef, useState } from 'react'

function formatTs(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function HashCell({ hash }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    if (!hash) return
    try {
      await navigator.clipboard.writeText(hash)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  if (!hash) return <span>—</span>

  return (
    <div className="manager-hash-cell">
      <code className="manager-hash-text">{hash}</code>
      <button
        className="manager-hash-copy"
        onClick={handleCopy}
        title="Copiar hash"
      >
        {copied ? '✓' : '📋'}
      </button>
    </div>
  )
}

export default function ChannelManager({ channels, onSave, onDelete }) {
  const [drafts, setDrafts] = useState({})
  const [savingIds, setSavingIds] = useState({})
  const titleSaveTimers = useRef({})

  const rows = useMemo(() => channels.slice().sort((a, b) => a.id - b.id), [channels])

  const getDraft = (ch) => drafts[ch.id] ?? { title: ch.title, enabled: !!ch.enabled }

  const setDraft = (id, patch, original) => {
    const base = drafts[id] ?? { title: original.title, enabled: !!original.enabled }
    setDrafts((prev) => ({ ...prev, [id]: { ...base, ...patch } }))
  }

  useEffect(() => {
    return () => {
      Object.values(titleSaveTimers.current).forEach((timerId) => clearTimeout(timerId))
    }
  }, [])

  const saveDraft = async (ch, candidate) => {
    const d = candidate ?? getDraft(ch)
    if (d.title === ch.title && d.enabled === !!ch.enabled) return

    setSavingIds((prev) => ({ ...prev, [ch.id]: true }))
    try {
      const ok = await onSave(ch.id, { title: d.title, enabled: d.enabled })
      if (ok === false) return
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[ch.id]
        return next
      })
    } finally {
      setSavingIds((prev) => ({ ...prev, [ch.id]: false }))
    }
  }

  const scheduleTitleSave = (ch, nextDraft) => {
    const timerId = titleSaveTimers.current[ch.id]
    if (timerId) clearTimeout(timerId)
    titleSaveTimers.current[ch.id] = setTimeout(() => {
      delete titleSaveTimers.current[ch.id]
      void saveDraft(ch, nextDraft)
    }, 600)
  }

  const handleDelete = async (ch) => {
    const ok = window.confirm(`Vols eliminar definitivament el canal "${ch.title}"?`)
    if (!ok) return
    setSavingIds((prev) => ({ ...prev, [ch.id]: true }))
    try {
      await onDelete(ch.id)
    } finally {
      setSavingIds((prev) => ({ ...prev, [ch.id]: false }))
    }
  }

  return (
    <div className="manager-wrap">
      <div className="section-title">Gestió de canals</div>
      {rows.length === 0 ? (
        <div className="empty-state">
          <span className="icon">🗂️</span>
          <span>No hi ha canals per gestionar.</span>
        </div>
      ) : (
        <div className="manager-table">
          <div className="manager-head">
            <span>ID</span>
            <span>Canal</span>
            <span>Hash</span>
            <span>Actiu</span>
            <span>Darrera comprovació</span>
            <span>Accions</span>
          </div>
          {rows.map((ch) => {
            const d = getDraft(ch)
            const busy = !!savingIds[ch.id]
            return (
              <div className="manager-row" key={ch.id}>
                <span className="manager-id">
                  <span className={`manager-status-dot ${ch.status ?? 'unknown'}`} />
                  #{ch.id}
                </span>
                <input
                  className="manager-title"
                  value={d.title}
                  maxLength={255}
                  disabled={busy}
                  onChange={(e) => {
                    const nextTitle = e.target.value
                    const nextDraft = { title: nextTitle, enabled: d.enabled }
                    setDraft(ch.id, { title: nextTitle }, ch)
                    scheduleTitleSave(ch, nextDraft)
                  }}
                />
                <HashCell hash={ch.hash} />
                <label className="manager-switch">
                  <input
                    type="checkbox"
                    checked={d.enabled}
                    disabled={busy}
                    onChange={(e) => {
                      const nextEnabled = e.target.checked
                      const nextDraft = { title: d.title, enabled: nextEnabled }
                      const timerId = titleSaveTimers.current[ch.id]
                      if (timerId) {
                        clearTimeout(timerId)
                        delete titleSaveTimers.current[ch.id]
                      }
                      setDraft(ch.id, { enabled: nextEnabled }, ch)
                      void saveDraft(ch, nextDraft)
                    }}
                  />
                  <span>{d.enabled ? 'Sí' : 'No'}</span>
                </label>
                <span className="manager-time">{formatTs(ch.last_checked)}</span>
                <div className="manager-actions">
                  <button className="stop-btn" disabled={busy} onClick={() => handleDelete(ch)}>
                    Elimina
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
