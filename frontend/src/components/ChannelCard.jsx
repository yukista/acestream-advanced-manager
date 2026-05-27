import { useEffect, useMemo, useRef, useState } from 'react'

const STATUS_ICON = { ok: '✅', error: '🔴', unknown: '⏳' }
const STATUS_LABEL = { ok: 'Actiu', error: 'Error', unknown: 'Comprovant…' }
const STATUS_PH_ICON = { ok: '🎬', error: '⚠️', unknown: '🔄' }

export default function ChannelCard({ channel, isActive, onWatch, onCheck }) {
  const videoRef = useRef(null)
  const modalVideoRef = useRef(null)
  const [playingInline, setPlayingInline] = useState(false)
  const [viewerOpen, setViewerOpen] = useState(false)
  const [viewerMode, setViewerMode] = useState('snapshot')

  const hasClip = channel.status === 'ok' && (channel.clip_id || channel.clip_url)
  const cacheBuster = channel.last_checked ?? Date.now()

  const snapshotSrc = useMemo(
    () => (hasClip ? `/api/channels/${channel.id}/snapshot?t=${cacheBuster}` : ''),
    [hasClip, channel.id, cacheBuster],
  )
  const clipSrc = useMemo(
    () => (hasClip ? `/api/channels/${channel.id}/clip?t=${cacheBuster}` : ''),
    [hasClip, channel.id, cacheBuster],
  )

  useEffect(() => {
    setPlayingInline(false)
    setViewerMode('snapshot')
  }, [channel.id, channel.last_checked, channel.clip_id, channel.clip_url])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !playingInline || !clipSrc) return
    video.play().catch(() => {})
  }, [playingInline, clipSrc])

  useEffect(() => {
    const video = modalVideoRef.current
    if (!video || !viewerOpen || viewerMode !== 'video' || !clipSrc) return
    video.play().catch(() => {})
  }, [viewerOpen, viewerMode, clipSrc])

  const openViewer = (mode) => {
    setViewerMode(mode)
    setViewerOpen(true)
  }

  const closeViewer = () => {
    setViewerOpen(false)
    setViewerMode('snapshot')
  }

  const handleInlinePlay = () => {
    if (!hasClip) return
    setPlayingInline(true)
  }

  const stopInlinePlay = () => {
    const video = videoRef.current
    if (video) {
      video.pause()
      video.currentTime = 0
    }
    setPlayingInline(false)
  }

  const handleModalVideoEnd = () => {
    const video = modalVideoRef.current
    if (video) {
      video.pause()
      video.currentTime = 0
    }
    setViewerMode('snapshot')
  }

  return (
    <div className={`channel-card${isActive ? ' active-ch' : ''}`}>
      <div className="card-thumb">
        {hasClip ? (
          <>
            {!playingInline ? (
              <>
                <img className="card-thumb-image" src={snapshotSrc} alt={`Captura de ${channel.title}`} loading="lazy" />
                <div className="card-thumb-tools">
                  <button className="thumb-btn" onClick={handleInlinePlay} title="Reproduir clip una vegada">
                    ▶ Clip
                  </button>
                  <button className="thumb-btn" onClick={() => openViewer('snapshot')} title="Veure gran">
                    ⛶ Gran
                  </button>
                </div>
              </>
            ) : (
              <video
                ref={videoRef}
                className="card-thumb-video"
                src={clipSrc}
                playsInline
                preload="metadata"
                autoPlay
                controls
                onEnded={stopInlinePlay}
                onError={stopInlinePlay}
              />
            )}
          </>
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
        {hasClip && (
          <button
            className="btn-check"
            onClick={() => openViewer('video')}
            title="Veure clip en gran"
          >
            🎬
          </button>
        )}
      </div>

      {viewerOpen && (
        <div className="preview-modal" onClick={closeViewer}>
          <div className="preview-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="preview-modal-head">
              <strong>{channel.title}</strong>
              <div className="preview-modal-actions">
                <button className="btn-check" onClick={() => setViewerMode('snapshot')}>Captura</button>
                <button className="btn-check" onClick={() => setViewerMode('video')}>Clip</button>
                <button className="btn-check" onClick={closeViewer}>Tancar</button>
              </div>
            </div>
            <div className="preview-modal-body">
              {viewerMode === 'video' ? (
                <video
                  ref={modalVideoRef}
                  className="preview-modal-media"
                  src={clipSrc}
                  controls
                  playsInline
                  preload="metadata"
                  autoPlay
                  onEnded={handleModalVideoEnd}
                  onError={handleModalVideoEnd}
                />
              ) : (
                <img className="preview-modal-media" src={snapshotSrc} alt={`Captura gran de ${channel.title}`} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
