import { useEffect, useRef } from 'react'
import Hls from 'hls.js'

export default function StreamPlayer({ src, channelName, onStop }) {
  const videoRef = useRef(null)
  const hlsRef = useRef(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    if (hlsRef.current) {
      hlsRef.current.destroy()
      hlsRef.current = null
    }

    if (!src) return

    if (Hls.isSupported()) {
      const hls = new Hls({
        maxBufferLength: 30,
        maxMaxBufferLength: 60,
        liveSyncDurationCount: 3,
        liveMaxLatencyDurationCount: 6,
        enableWorker: true,
      })
      hlsRef.current = hls
      hls.loadSource(src)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {})
      })
      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (data.fatal) {
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            hls.startLoad()
          } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
            hls.recoverMediaError()
          }
        }
      })
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      video.play().catch(() => {})
    }

    return () => {
      hlsRef.current?.destroy()
      hlsRef.current = null
    }
  }, [src])

  if (!src) {
    return (
      <div className="player-wrap">
        <div className="player-empty">
          <span className="icon">📺</span>
          <span>Selecciona un canal per veure el stream en viu</span>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="player-wrap">
        <video ref={videoRef} controls playsInline />
      </div>
      {channelName && (
        <div className="player-info">
          <span className="live-badge">EN VIU</span>
          <span className="player-channel-name">{channelName}</span>
          <button className="stop-btn" onClick={onStop}>■ Atura</button>
        </div>
      )}
    </>
  )
}
