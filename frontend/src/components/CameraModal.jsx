import { useRef, useEffect } from 'react'

export default function CameraModal({ open, onClose, onCapture }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      .then(stream => {
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return }
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
      })
      .catch(() => {
        alert('Camera access was blocked or is unavailable. You can upload a photo instead.')
        onClose()
      })
    return () => {
      cancelled = true
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop())
    }
  }, [open])

  if (!open) return null

  function handleShoot() {
    const video = videoRef.current
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    canvas.toBlob(blob => {
      onCapture(blob)
      onClose()
    }, 'image/jpeg', 0.9)
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-head">
          <h3>Capture photo</h3>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M6 6l12 12M18 6 6 18" stroke="#2F4A3D" strokeWidth="2" strokeLinecap="round" /></svg>
          </button>
        </div>
        <video ref={videoRef} className="camera-video" autoPlay playsInline />
        <div className="camera-actions">
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={handleShoot}>Capture</button>
        </div>
      </div>
    </div>
  )
}
