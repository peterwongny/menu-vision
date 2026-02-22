import { useEffect, useState } from 'react';
import apiClient from './api';
import DishCard from './DishCard';
import type { MenuResult } from './types';

interface ResultsPageProps {
  jobId: string;
  onBack: () => void;
}

export default function ResultsPage({ jobId, onBack }: ResultsPageProps) {
  const [result, setResult] = useState<MenuResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const { data } = await apiClient.get<MenuResult>(`/jobs/${jobId}`);
        if (cancelled) return;
        setResult(data);

        if (data.status === 'processing') {
          timer = setTimeout(poll, 2000);
        }
      } catch {
        if (!cancelled) setError('Failed to fetch results. Please try again.');
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId]);

  if (error) {
    return (
      <div className="results-page">
        <p className="results-error" role="alert">{error}</p>
        <button className="btn btn-secondary" onClick={onBack}>← Try another menu</button>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="results-page">
        <div className="processing-indicator" role="status" aria-label="Processing your menu">
          <div className="spinner" />
          <p>Processing your menu…</p>
        </div>
      </div>
    );
  }

  const isProcessing = result.status === 'processing';
  const dishesWithImages = result.dishes.filter(
    d => d.image_url && d.image_url !== 'placeholder://no-image'
  );
  const totalDishes = result.dishes.length;

  return (
    <div className="results-page">
      <div className="results-header">
        <button className="btn btn-secondary" onClick={onBack}>← New scan</button>
        {result.source_language && (
          <span>Detected: {result.source_language}</span>
        )}
        {isProcessing && totalDishes > 0 && (
          <span className="progress-text">
            Generating images… {dishesWithImages.length}/{totalDishes}
          </span>
        )}
      </div>

      {isProcessing && totalDishes === 0 && (
        <div className="processing-indicator" role="status" aria-label="Processing your menu">
          <div className="spinner" />
          <p>Processing your menu…</p>
        </div>
      )}

      {result.error_message && (
        <p className="results-error" role="alert">{result.error_message}</p>
      )}

      {totalDishes > 0 ? (
        <div className="dish-grid">
          {result.dishes.map((dish, i) => (
            <DishCard key={i} dish={dish} />
          ))}
        </div>
      ) : (
        !isProcessing && <p>No dishes found in this menu.</p>
      )}

      {isProcessing && totalDishes > 0 && (
        <div className="processing-footer" role="status">
          <div className="spinner spinner-small" />
          <span>Still generating images…</span>
        </div>
      )}
    </div>
  );
}
