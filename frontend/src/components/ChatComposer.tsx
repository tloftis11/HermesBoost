import { useState } from "react";

interface ChatComposerProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export function ChatComposer({ onSend, disabled }: ChatComposerProps) {
  const [value, setValue] = useState("");

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="composer">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
        placeholder="Describe what to adjust..."
        disabled={disabled}
      />
      <button type="button" className="btn primary" onClick={submit} disabled={disabled || !value.trim()}>
        {disabled ? "Sending…" : "Send"}
      </button>
    </div>
  );
}
