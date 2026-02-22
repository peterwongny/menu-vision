import { useRef, useState, useCallback, useEffect } from 'react';

interface CameraCaptureProps {
  onCapture: (file: File) => void;
  onClose: () => void;
}

export default function CameraCapture({ onCapture, onClose }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function startCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: 'environment',
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
          audio: false,
        });

        if (cancelled) {
          stream.getTracks().forEach(t => t.stop());
          return;
        }

        streamRef.current = stream;

        // Turn off torch/flash if supported
        const track = stream.getVideoTracks()[0];
        const capabilities = track.getCapabilities?.() as Record<string, unknown> | undefined;
        if (capabilities?.torch) {
          await track.applyConstraints({ advanced: [{ torch: false } as MediaTrackConstraintSet] });
        }

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
          setReady(true);
        }
      } catch {
        if (!cancelled) setError('Could not access camera. Please use the upload button instead.');
      }
    }

    startCamera();
    return () => {
      cancelled = true;
      stopStream();
    };
  }, [stopStream]);

  function capture() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (blob) {
          const file = new File([blob], 'menu_photo.jpg', { type: 'image/jpeg' });
          stopStream();
          onCapture(file);
        }
      },
      'image/jpeg',
      0.85,
    );
  }

  if (error) {
    return (
      <div className="camera-overlay">
        <div className="camera-error">
          <p>{error}</p>
          <button className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    );
  }

  return (
    <div className="camera-overlay">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="camera-viewfinder"
      />
      <canvas ref={canvasRef} hidden />
      <div className="camera-controls">
        <button className="btn btn-secondary" onClick={() => { stopStream(); onClose(); }}>
          Cancel
        </button>
        {ready && (
          <button className="btn btn-capture" onClick={capture} aria-label="Take photo">
            <span className="capture-circle" />
          </button>
        )}
      </div>
    </div>
  );
}
