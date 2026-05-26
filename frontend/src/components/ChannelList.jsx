import { useState } from 'react'

function formatLastChecked(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function ChannelList({ channels, activeChannelId, onSwitch, onAdd }) {
  const [title, setTitle] = useState('')
  const [hash, setHash] = useState('')
  const [adding, setAdding] = useState(false)

  const handleAdd = async (e) => {
    e.preventDefault()
    if (!title.trim() || hash.length !== 40) return
    setAdding(true)
    try {
      await onAdd(title.trim(), hash.trim().toLowerCase())
      setTitle('')
      setHash('')
    } finally {
      setAdding(false)
    }
  }

  return (
    <>
      <div className="sidebar-header">
        <span>Canals ({channels.length})</span>
      </div>

      <div className="sidebar-list">
        {channels.length === 0 && (
          <div style={{ padding: '16px 12px', color: 'var(--muted)', fontSize: '12px' }}>
            Afegeix el primer canal ↓
          </div>
        )}
        {channels.map((ch) => (
          <div
            key={ch.id}
            className={`channel-row${ch.id === activeChannelId ? ' active' : ''}`}
            onClick={() => onSwitch(ch.id)}
            title={ch.hash}
          >
            <span className={`status-dot ${ch.status}`} />
            <span className="ch-title">{ch.title}</span>
            {ch.resolution && <span className="ch-res">{ch.resolution}</span>}
            <span className="ch-last">{formatLastChecked(ch.last_checked)}</span>
          </div>
        ))}
      </div>

      <form className="add-form" onSubmit={handleAdd}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, flex: 1 }}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Títol del canal"
            maxLength={255}
          />
          <input
            value={hash}
            onChange={(e) => setHash(e.target.value)}
            placeholder="Hash (40 hex)"
            maxLength={40}
            spellCheck={false}
          />
        </div>
        <button
          type="submit"
          className="btn-add"
          disabled={adding || !title.trim() || hash.length !== 40}
        >
          {adding ? <span className="spinner" /> : '+'}
        </button>
      </form>
    </>
  )
}
