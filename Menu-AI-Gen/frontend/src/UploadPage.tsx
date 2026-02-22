import { useRef, useState } from 'react';
import { validateFile } from './validation';
import apiClient from './api';

interface UploadPageProps {
  onJobCreated: (jobId: string) => void;
}

export default function UploadPage({ onJobCreated }: UploadPageProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  async function handleFile(file: File) {
    setError(null);
    const result = validateFile(file);
    if (!result.valid) {
      setError(result.error ?? 'Invalid file');
      return;
    }

    setUploading(true);
    setProgress(0);

    try {
      const { data } = await apiClient.post<{ jobId: string; uploadUrl: string }>('/jobs');
      const { jobId, uploadUrl } = data;

      const response = await fetch(uploadUrl, {
        method: 'PUT',
        body: file,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.status}`);
      }

      setProgress(100);
      onJobCreated(jobId);
    } catch {
      setError('Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = '';
  }

  return (
    <div className="upload-page">
      <p className="upload-instructions">
        Take a photo of a restaurant menu or upload an existing image.
      </p>

      <div className="upload-buttons">
        <button
          className="btn btn-primary"
          onClick={() => cameraInputRef.current?.click()}
          disabled={uploading}
          aria-label="Take a photo with your camera"
        >
          📷 Take Photo
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          aria-label="Upload an image file"
        >
          📁 Upload Image
        </button>
      </div>

      <input
        ref={cameraInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        onChange={onFileChange}
        hidden
        aria-hidden="true"
      />
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={onFileChange}
        hidden
        aria-hidden="true"
      />

      {uploading && (
        <div className="upload-progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-bar" style={{ width: `${progress}%` }} />
          <span className="progress-label">Uploading…</span>
        </div>
      )}

      {error && (
        <p className="upload-error" role="alert">{error}</p>
      )}
    </div>
  );
}
