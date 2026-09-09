interface AiSummaryCardProps {
  aiDescription: string | null;
  pending: boolean;
}

export function AiSummaryCard({ aiDescription, pending }: AiSummaryCardProps) {
  return (
    <div className="card ai-summary">
      <div className="spark">
        <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
          <path d="M10 3l1.4 4.6L16 9l-4.6 1.4L10 15l-1.4-4.6L4 9l4.6-1.4L10 3Z" fill="currentColor" />
        </svg>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h3>Auto-generated description</h3>
        {pending || aiDescription === null ? (
          <div>
            <div className="skeleton-line" />
            <div className="skeleton-line" />
          </div>
        ) : (
          <>
            <p>{aiDescription}</p>
            <button type="button" className="correction-link" disabled title="Coming soon">
              Suggest a correction
            </button>
          </>
        )}
      </div>
    </div>
  );
}
