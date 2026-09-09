interface UploadDropzoneProps {
  onTriggerUpload: () => void;
  uploading: boolean;
}

// Shares one hidden file input (owned by UploadProfilePage) with the topbar
// "Upload dataset" button, rather than each surface owning its own input.
export function UploadDropzone({ onTriggerUpload, uploading }: UploadDropzoneProps) {
  return (
    <button type="button" className="upload-zone" onClick={onTriggerUpload} disabled={uploading}>
      <svg width="15" height="15" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 6.5v7M6.5 10h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      {uploading ? "Uploading…" : "Upload new dataset"}
    </button>
  );
}
