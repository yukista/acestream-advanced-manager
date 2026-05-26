import { useMemo, useState } from 'react'

function formatTs(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function ChannelManager({ channels, onSave, onDelete }) {
  const [drafts, setDrafts] = useState({})
  const [savingIds, setSavingIds] = useState({})

  const rows = useMemo(() => channels.slice().sort((a, b) => a.id - b.id), [channels])

  const getDraft = (ch) => drafts[ch.id] ?? { title: ch.title, enabled: !!ch.enabled }

  const setDraft = (id, patch, original) => {
    const base = drafts[id] ?? { title: original.title, enabled: !!original.enabled }
    setDrafts((prev) => ({ ...prev, [id]: { ...base, ...patch } }))
  }

  const handleSave = async (ch) => {
    const d = getDraft(ch)
    if (d.title === ch.title && d.enabled === !!ch.enabled) return

    setSavingIds((prev) => ({ ...prev, [ch.id]: true }))
    try {
      await onSave(ch.id, { title: d.title, enabled: d.enabled })
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[ch.id]
        return next
      })
    } finally {
      setSavingIds((prev) => ({ ...prev, [ch.id]: false }))
    }
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
            <span>Actiu</span>
            <span>Darrera comprovació</span>
            <span>Accions</span>
          </div>
          {rows.map((ch) => {
            const d = getDraft(ch)
            const dirty = d.title !== ch.title || d.enabled !== !!ch.enabled
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
                  onChange={(e) => setDraft(ch.id, { title: e.target.value }, ch)}
                />
                <label className="manager-switch">
                  <input
                    type="checkbox"
                    checked={d.enabled}
                    onChange={(e) => setDraft(ch.id, { enabled: e.target.checked }, ch)}
                  />
                  <span>{d.enabled ? 'Sí' : 'No'}</span>
                </label>
                <span className="manager-time">{formatTs(ch.last_checked)}</span>
                <div className="manager-actions">
                  <button className="btn-check" disabled={!dirty || busy} onClick={() => handleSave(ch)}>
                    {busy ? '...' : 'Desa'}
                  </button>
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
