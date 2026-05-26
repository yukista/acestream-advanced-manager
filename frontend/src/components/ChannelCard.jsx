import { useRef, useEffect } from 'react'

const STATUS_ICON = { ok: '✅', error: '🔴', unknown: '⏳' }
const STATUS_LABEL = { ok: 'Actiu', error: 'Error', unknown: 'Comprovant…' }
const STATUS_PH_ICON = { ok: '🎬', error: '⚠️', unknown: '🔄' }

export default function ChannelCard({ channel, isActive, onWatch, onCheck }) {
  const videoRef = useRef(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (channel.clip_id || channel.clip_url) {
      const cacheBuster = channel.last_checked ?? Date.now()
      video.src = `/api/channels/${channel.id}/clip?t=${cacheBuster}`
      video.load()
      video.play().catch(() => {})
    }
    return () => {
      if (video) {
        video.pause()
        video.src = ''
      }
    }
  }, [channel.id, channel.clip_id, channel.clip_url, channel.last_checked])

  const hasClip = channel.status === 'ok' && (channel.clip_id || channel.clip_url)

  return (
    <div className={`channel-card${isActive ? ' active-ch' : ''}`}>
      <div className="card-thumb">
        {hasClip ? (
          <video
            ref={videoRef}
            muted
            loop
            playsInline
            preload="metadata"
          />
        ) : (
          <div className="card-thumb-placeholder">
            <span className="ph-icon">{STATUS_PH_ICON[channel.status] ?? '📡'}</span>
            <span className="ph-msg">
              {channel.status === 'error'
                ? channel.error_message ?? 'Stream no disponible'
                : channel.status === 'unknown'
                ? 'Comprovant disponibilitat…'
                : 'Sense clip'}
            </span>
          </div>
        )}
      </div>

      <div className="card-body">
        <span className="card-title" title={channel.title}>{channel.title}</span>
        <div className="card-meta">
          <span className={`status-badge ${channel.status}`}>
            <span className="status-dot" />
            {STATUS_LABEL[channel.status] ?? channel.status}
          </span>
          {channel.resolution && (
            <span className="card-res">{channel.resolution}</span>
          )}
        </div>
      </div>

      <div className="card-actions">
        <button
          className="btn-watch"
          onClick={() => onWatch(channel.id)}
          title="Veure en directe"
        >
          ▶ Veure
        </button>
        <button
          className="btn-check"
          onClick={() => onCheck(channel.id)}
          title="Comprovar ara"
        >
          ↺
        </button>
      </div>
    </div>
  )
}
