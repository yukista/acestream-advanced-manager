import { useState, useEffect, useCallback, useRef } from 'react'
import ChannelList from './components/ChannelList'
import StreamPlayer from './components/StreamPlayer'
import ChannelCard from './components/ChannelCard'
import ChannelManager from './components/ChannelManager'
import ConfigPanel from './components/ConfigPanel'

const API = '/api'

function formatTs(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function checkerLabel(r) {
  if (r?.checker_name) return r.checker_name
  if (r?.checker_url) {
    try {
      return new URL(r.checker_url).hostname
    } catch {
      return r.checker_url
    }
  }
  return '—'
}

export default function App() {
  const [channels, setChannels] = useState([])       // enabled channels only
  const [allChannels, setAllChannels] = useState([]) // includes disabled
  const [channelMap, setChannelMap] = useState({})   // id → channel
  const [stream, setStream] = useState(null)          // active stream info
  const [checkStatus, setCheckStatus] = useState(null) // health-check task status
  const [settings, setSettings] = useState(null)
  const [sseConnected, setSseConnected] = useState(false)
  const [tab, setTab] = useState('live')
  const [error, setError] = useState(null)
  const [nowTs, setNowTs] = useState(Math.floor(Date.now() / 1000))
  const sseRef = useRef(null)

  useEffect(() => {
    const t = setInterval(() => {
      setNowTs(Math.floor(Date.now() / 1000))
    }, 1000)
    return () => clearInterval(t)
  }, [])

  const formatElapsed = useCallback((fromTs) => {
    if (!fromTs) return '—'
    const delta = Math.max(0, nowTs - fromTs)
    if (delta < 60) {
      return `${delta}s`
    }
    if (delta < 3600) {
      return `${Math.floor(delta / 60)}m`
    }
    const h = Math.floor(delta / 3600)
    const m = Math.floor((delta % 3600) / 60)
    return `${h}h ${m}m`
  }, [nowTs])

  // ── Fetch all channels ────────────────────────────────────────────────────
  const fetchChannels = useCallback(async () => {
    try {
      const res = await fetch(`${API}/channels`)
      if (!res.ok) return
      const data = await res.json()
      setChannels(data)
      setChannelMap((prev) => ({ ...prev, ...Object.fromEntries(data.map((c) => [c.id, c])) }))
    } catch (e) {
      console.error('fetchChannels', e)
    }
  }, [])

  const fetchAllChannels = useCallback(async () => {
    try {
      const res = await fetch(`${API}/channels?include_disabled=true`)
      if (!res.ok) return
      const data = await res.json()
      setAllChannels(data)
      setChannelMap(Object.fromEntries(data.map((c) => [c.id, c])))
      setChannels(data.filter((c) => c.enabled !== false))
    } catch (e) {
      console.error('fetchAllChannels', e)
    }
  }, [])

  // ── Fetch single channel (for SSE updates) ────────────────────────────────
  const fetchChannel = useCallback(async (id) => {
    try {
      const res = await fetch(`${API}/channels/${id}`)
      if (!res.ok) return
      const ch = await res.json()
      setChannelMap((prev) => ({ ...prev, [id]: ch }))

      setAllChannels((prev) => {
        const exists = prev.some((c) => c.id === id)
        if (!exists) return [...prev, ch].sort((a, b) => a.id - b.id)
        return prev.map((c) => (c.id === id ? ch : c))
      })

      setChannels((prev) => {
        const exists = prev.some((c) => c.id === id)
        if (ch.enabled === false) {
          return prev.filter((c) => c.id !== id)
        }
        if (!exists) return [...prev, ch].sort((a, b) => a.id - b.id)
        return prev.map((c) => (c.id === id ? ch : c))
      })

      if (stream?.channel_id === id && ch.enabled === false) {
        setStream(null)
      }
    } catch (e) {
      console.error('fetchChannel', e)
    }
  }, [stream])

  // ── Fetch active stream ───────────────────────────────────────────────────
  const fetchStream = useCallback(async () => {
    try {
      const res = await fetch(`${API}/stream`)
      if (!res.ok) return
      const data = await res.json()
      setStream(data.active ? data : null)
    } catch (e) {
      console.error('fetchStream', e)
    }
  }, [])

  const fetchCheckStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/health-check/status`)
      if (!res.ok) return
      const data = await res.json()
      setCheckStatus(data)
    } catch (e) {
      console.error('fetchCheckStatus', e)
    }
  }, [])

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API}/settings`)
      if (!res.ok) return
      const data = await res.json()
      setSettings(data)
    } catch (e) {
      console.error('fetchSettings', e)
    }
  }, [])

  // ── SSE connection ────────────────────────────────────────────────────────
  useEffect(() => {
    let es
    let retry

    const connect = () => {
      es = new EventSource(`${API}/events`)
      sseRef.current = es

      es.addEventListener('connected', () => setSseConnected(true))

      es.addEventListener('channel_updated', (e) => {
        const { channel_id } = JSON.parse(e.data)
        fetchChannel(channel_id)
      })

      es.addEventListener('stream_changed', (e) => {
        const { channel_id, started_at } = JSON.parse(e.data)
        setStream({ active: true, channel_id, started_at })
        setTab('live')
      })

      es.addEventListener('stream_stopped', () => {
        setStream(null)
      })

      es.addEventListener('health_check_status', (e) => {
        setCheckStatus(JSON.parse(e.data))
      })

      es.addEventListener('settings_updated', (e) => {
        setSettings(JSON.parse(e.data))
      })

      es.onerror = () => {
        setSseConnected(false)
        es.close()
        retry = setTimeout(connect, 3000)
      }
    }

    connect()
    return () => {
      clearTimeout(retry)
      es?.close()
    }
  }, [fetchChannel])

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    fetchAllChannels()
    fetchStream()
    fetchCheckStatus()
    fetchSettings()
  }, [fetchAllChannels, fetchStream, fetchCheckStatus, fetchSettings])

  // ── Actions ───────────────────────────────────────────────────────────────
  const handleAddChannel = async (title, hash) => {
    const res = await fetch(`${API}/channels`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, hash }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      setError(err.detail ?? 'Error afegint canal')
      setTimeout(() => setError(null), 4000)
      return
    }
    await fetchAllChannels()
  }

  const handleWatchChannel = async (channelId) => {
    setError(null)
    setTab('live')
    const res = await fetch(`${API}/stream/switch/${channelId}`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      setError(err.detail ?? 'Error canviant canal')
      setTimeout(() => setError(null), 5000)
    }
    // stream_changed SSE event will update the state
  }

  const handleStopStream = async () => {
    await fetch(`${API}/stream`, { method: 'DELETE' })
    // stream_stopped SSE event will update the state
  }

  const handleCheck = async (channelId) => {
    await fetch(`${API}/channels/${channelId}/check`, { method: 'POST' })
  }

  const handleSaveChannel = async (channelId, payload) => {
    const res = await fetch(`${API}/channels/${channelId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      setError(err.detail ?? 'Error desant canal')
      setTimeout(() => setError(null), 4000)
      return false
    }
    await fetchAllChannels()
    await fetchStream()
    return true
  }

  const handleDeleteChannel = async (channelId) => {
    const res = await fetch(`${API}/channels/${channelId}`, { method: 'DELETE' })
    if (!res.ok && res.status !== 204) {
      const err = await res.json().catch(() => ({}))
      setError(err.detail ?? 'Error eliminant canal')
      setTimeout(() => setError(null), 4000)
      return
    }
    await fetchAllChannels()
    await fetchStream()
  }

  const handleUpdateSettings = async (values) => {
    const res = await fetch(`${API}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      setError(err.detail ?? 'Error desant configuració')
      setTimeout(() => setError(null), 4000)
      return false
    }
    const data = await res.json()
    setSettings(data)
    return true
  }

  const handleResetSettings = async () => {
    const ok = window.confirm('Vols restaurar la configuració per defecte?')
    if (!ok) return false
    const res = await fetch(`${API}/settings/reset`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      setError(err.detail ?? 'Error restaurant configuració')
      setTimeout(() => setError(null), 4000)
      return false
    }
    const data = await res.json()
    setSettings(data)
    return true
  }

  // ── Derived ───────────────────────────────────────────────────────────────
  const activeChannelId = stream?.channel_id ?? null
  const activeChannel = activeChannelId ? channelMap[activeChannelId] : null
  const streamVersion = stream?.started_at ?? stream?.channel_id ?? '0'
  const streamSrc = stream?.active
    ? `${API}/stream/playlist.m3u8?v=${encodeURIComponent(streamVersion)}`
    : null

  return (
    <div className="app">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="header">
        <span className="header-logo">📺 Ace<span>Stream TV</span></span>
        <span className="header-spacer" />
        {error && (
          <span style={{ color: 'var(--error)', fontSize: 12, marginRight: 12 }}>
            ⚠ {error}
          </span>
        )}
        <span
          className={`sse-dot${sseConnected ? ' connected' : ''}`}
          title={sseConnected ? 'Connectat en temps real' : 'Reconnectant…'}
        />
      </header>

      {/* ── Sidebar ────────────────────────────────────────────────────── */}
      <aside className="sidebar">
        <ChannelList
          channels={channels}
          activeChannelId={activeChannelId}
          onSwitch={handleWatchChannel}
          onAdd={handleAddChannel}
        />
      </aside>

      {/* ── Main ───────────────────────────────────────────────────────── */}
      <main className="main">
        <nav className="main-tabs">
          <button
            className={`tab-btn${tab === 'live' ? ' active' : ''}`}
            onClick={() => setTab('live')}
          >
            ▶ En Directe
          </button>
          <button
            className={`tab-btn${tab === 'channels' ? ' active' : ''}`}
            onClick={() => setTab('channels')}
          >
            📋 Canals ({channels.length})
          </button>
          <button
            className={`tab-btn${tab === 'checks' ? ' active' : ''}`}
            onClick={() => setTab('checks')}
          >
            🧪 Comprovacions
          </button>
          <button
            className={`tab-btn${tab === 'manage' ? ' active' : ''}`}
            onClick={() => setTab('manage')}
          >
            ⚙ Gestionar
          </button>
          <button
            className={`tab-btn${tab === 'config' ? ' active' : ''}`}
            onClick={() => setTab('config')}
          >
            🛠 Configuració
          </button>
        </nav>

        <div className="main-content">
          {/* ── Live tab ─────────────────────────────────────────────── */}
          {tab === 'live' && (
            <>
              <StreamPlayer
                src={streamSrc}
                channelName={activeChannel?.title}
                initialBufferSeconds={settings?.values?.stream_switch_buffer_seconds ?? 20}
                onStop={handleStopStream}
              />
              {!stream && channels.length > 0 && (
                <div className="section-title" style={{ textAlign: 'center', marginTop: 8 }}>
                  Selecciona un canal de la llista o fes clic a ▶ Veure en un canal
                </div>
              )}
            </>
          )}

          {/* ── Channels tab ─────────────────────────────────────────── */}
          {tab === 'channels' && (
            <>
              <div className="section-title">Tots els canals</div>
              {channels.length === 0 ? (
                <div className="empty-state">
                  <span className="icon">📡</span>
                  <span>Encara no hi ha canals. Afegeix-ne un a la barra lateral.</span>
                </div>
              ) : (
                <div className="channels-grid">
                  {channels.map((ch) => (
                    <ChannelCard
                      key={ch.id}
                      channel={channelMap[ch.id] ?? ch}
                      isActive={ch.id === activeChannelId}
                      onWatch={handleWatchChannel}
                      onCheck={handleCheck}
                    />
                  ))}
                </div>
              )}
            </>
          )}

          {/* ── Checks tab ───────────────────────────────────────────── */}
          {tab === 'checks' && (
            <>
              <div className="section-title">Estat de les comprovacions en temps real</div>
              {!checkStatus ? (
                <div className="empty-state">
                  <span className="icon">⏳</span>
                  <span>Carregant estat de comprovacions…</span>
                </div>
              ) : (
                <div className="checks-wrap">
                  <div className="checks-kpis">
                    <div className="check-kpi">
                      <span className="kpi-label">Estat</span>
                      <span className={`kpi-value ${checkStatus.running ? 'running' : 'idle'}`}>
                        {checkStatus.running ? 'En execució' : 'Aturat'}
                      </span>
                    </div>
                    <div className="check-kpi">
                      <span className="kpi-label">Cicle</span>
                      <span className="kpi-value">#{checkStatus.cycle_id ?? 0}</span>
                    </div>
                    <div className="check-kpi">
                      <span className="kpi-label">Progrés</span>
                      <span className="kpi-value">
                        {(checkStatus.checked_in_cycle ?? 0)}/{(checkStatus.total_channels_in_cycle ?? 0)}
                      </span>
                    </div>
                    <div className="check-kpi">
                      <span className="kpi-label">Interval</span>
                      <span className="kpi-value">{checkStatus.interval_seconds ?? 0}s</span>
                    </div>
                    <div className="check-kpi">
                      <span className="kpi-label">Instàncies</span>
                      <span className="kpi-value">
                        {(checkStatus.active_checker_instances ?? 1)}/{(checkStatus.available_checker_instances ?? 1)}
                      </span>
                    </div>
                    <div className="check-kpi">
                      <span className="kpi-label">Inici cicle</span>
                      <span className="kpi-value">{formatTs(checkStatus.last_cycle_started)}</span>
                    </div>
                    <div className="check-kpi">
                      <span className="kpi-label">Fi cicle</span>
                      <span className="kpi-value">{formatTs(checkStatus.last_cycle_finished)}</span>
                    </div>
                  </div>

                  <div className="checks-current">
                    <strong>Canal en comprovació:</strong>{' '}
                    {checkStatus.current_channel_title
                      ? `${checkStatus.current_channel_title} (id ${checkStatus.current_channel_id})`
                      : 'cap'}
                    {checkStatus.current_checker_url ? (
                      <>
                        {' · '}
                        <strong>Comprovador:</strong> {checkStatus.current_checker_name ?? checkerLabel(checkStatus)}
                      </>
                    ) : null}
                  </div>

                  <div className="checks-workers">
                    <div className="section-title" style={{ marginBottom: 8 }}>Comprovadors en temps real</div>
                    <div className="checks-workers-grid">
                      {Object.values(checkStatus.checker_workers ?? {}).map((w) => (
                        <div className="checker-card" key={w.checker_url}>
                          <div className="checker-head">
                            <span className="checker-name">{w.checker_name ?? checkerLabel(w)}</span>
                            <span className={`checker-state ${w.busy ? 'busy' : 'idle'}`}>
                              {w.enabled ? (w.busy ? 'Treballant' : 'Lliure') : 'Desactivat'}
                            </span>
                          </div>
                          <div className="checker-meta">
                            {w.busy
                              ? (w.current_channel_title
                                  ? `${w.current_channel_title} (id ${w.current_channel_id})`
                                  : 'Canal en curs…')
                              : 'Sense comprovació activa'}
                          </div>
                          <div className="checker-meta">
                            {w.busy
                              ? `Comprovant des de fa: ${formatElapsed(w.busy_since ?? w.last_started)}`
                              : `Darrera comprovació fa: ${formatElapsed(w.last_finished)}`}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="checks-recent">
                    <div className="section-title" style={{ marginBottom: 8 }}>Darrers resultats</div>
                    {(!checkStatus.recent_results || checkStatus.recent_results.length === 0) ? (
                      <div className="empty-state" style={{ minHeight: 120 }}>
                        <span className="icon">📝</span>
                        <span>Encara no hi ha execucions registrades.</span>
                      </div>
                    ) : (
                      <div className="checks-table">
                        {checkStatus.recent_results.map((r, i) => (
                          <div className="checks-row" key={`${r.channel_id ?? 'x'}-${r.checked_at ?? 0}-${i}`}>
                            <span className={`checks-status ${r.status === 'ok' ? 'ok' : 'error'}`}>
                              {r.status === 'ok' ? 'OK' : 'ERROR'}
                            </span>
                            <span className="checks-checker" title={r.checker_url ?? ''}>{checkerLabel(r)}</span>
                            <span className="checks-channel">{r.channel_title ?? `Canal ${r.channel_id ?? '-'}`}</span>
                            <span className="checks-time" title={formatTs(r.checked_at)}>{formatElapsed(r.checked_at)}</span>
                            <span className="checks-error">{r.error_message ?? '—'}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {/* ── Manage tab ───────────────────────────────────────────── */}
          {tab === 'manage' && (
            <ChannelManager
              channels={allChannels}
              onSave={handleSaveChannel}
              onDelete={handleDeleteChannel}
            />
          )}

          {/* ── Config tab ───────────────────────────────────────────── */}
          {tab === 'config' && (
            <ConfigPanel
              settings={settings}
              onSave={handleUpdateSettings}
              onReset={handleResetSettings}
              onRefresh={fetchSettings}
            />
          )}
        </div>
      </main>
    </div>
  )
}
