import { useEffect, useRef, useState } from 'react'
import Hls from 'hls.js'

function getBufferedAheadSeconds(video) {
  const ranges = video.buffered
  const ct = video.currentTime
  let containingRangeAhead = 0
  let longestRange = 0

  for (let i = 0; i < ranges.length; i += 1) {
    const start = ranges.start(i)
    const end = ranges.end(i)
    const len = Math.max(0, end - start)
    if (len > longestRange) longestRange = len

    if (ct >= start && ct <= end) {
      containingRangeAhead = Math.max(0, end - ct)
      break
    }
  }

  return containingRangeAhead > 0 ? containingRangeAhead : longestRange
}

export default function StreamPlayer({ src, channelName, initialBufferSeconds = 20, onStop }) {
  const videoRef = useRef(null)
  const hlsRef = useRef(null)
  const retryTimerRef = useRef(null)
  const monitorTimerRef = useRef(null)
  const [isBuffering, setIsBuffering] = useState(false)
  const [bufferedSeconds, setBufferedSeconds] = useState(0)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
    if (monitorTimerRef.current) {
      clearInterval(monitorTimerRef.current)
      monitorTimerRef.current = null
    }

    if (hlsRef.current) {
      hlsRef.current.destroy()
      hlsRef.current = null
    }

    if (!src) {
      setIsBuffering(false)
      setBufferedSeconds(0)
      return
    }

    const bufferTargetSeconds = Math.max(0, Number(initialBufferSeconds) || 0)
    const startPlaybackWhenReady = () => {
      const ahead = getBufferedAheadSeconds(video)
      setBufferedSeconds(ahead)

      if (ahead >= bufferTargetSeconds || bufferTargetSeconds === 0) {
        setIsBuffering(false)
        if (monitorTimerRef.current) {
          clearInterval(monitorTimerRef.current)
          monitorTimerRef.current = null
        }
        video.play().catch(() => {})
      } else {
        setIsBuffering(true)
      }
    }

    video.pause()
    setBufferedSeconds(0)
    setIsBuffering(bufferTargetSeconds > 0)

    if (Hls.isSupported()) {
      const hls = new Hls({
        maxBufferLength: 60,
        maxMaxBufferLength: 120,
        liveSyncDurationCount: 5,
        liveMaxLatencyDurationCount: 10,
        manifestLoadingMaxRetry: 12,
        manifestLoadingRetryDelay: 500,
        levelLoadingMaxRetry: 8,
        levelLoadingRetryDelay: 500,
        enableWorker: true,
      })
      hlsRef.current = hls
      hls.loadSource(src)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, startPlaybackWhenReady)
      hls.on(Hls.Events.FRAG_BUFFERED, startPlaybackWhenReady)
      hls.on(Hls.Events.LEVEL_LOADED, startPlaybackWhenReady)

      monitorTimerRef.current = setInterval(startPlaybackWhenReady, 300)
      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (data.fatal) {
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            if (retryTimerRef.current) {
              clearTimeout(retryTimerRef.current)
            }
            retryTimerRef.current = setTimeout(() => {
              if (!hlsRef.current) return
              hls.stopLoad()
              hls.loadSource(src)
              hls.startLoad(-1)
              startPlaybackWhenReady()
            }, 800)
          } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
            hls.recoverMediaError()
          }
        }
      })
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      const onLoadedData = () => startPlaybackWhenReady()
      video.addEventListener('loadeddata', onLoadedData)
      monitorTimerRef.current = setInterval(startPlaybackWhenReady, 300)

      return () => {
        video.removeEventListener('loadeddata', onLoadedData)
        if (monitorTimerRef.current) {
          clearInterval(monitorTimerRef.current)
          monitorTimerRef.current = null
        }
        if (retryTimerRef.current) {
          clearTimeout(retryTimerRef.current)
          retryTimerRef.current = null
        }
        hlsRef.current?.destroy()
        hlsRef.current = null
      }
    }

    return () => {
      if (monitorTimerRef.current) {
        clearInterval(monitorTimerRef.current)
        monitorTimerRef.current = null
      }
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current)
        retryTimerRef.current = null
      }
      hlsRef.current?.destroy()
      hlsRef.current = null
    }
  }, [src, initialBufferSeconds])

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
        {isBuffering && (
          <div className="player-buffering">
            <div>Buffering...</div>
            <div>{Math.floor(bufferedSeconds)}s / {Math.floor(Math.max(0, Number(initialBufferSeconds) || 0))}s</div>
          </div>
        )}
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
