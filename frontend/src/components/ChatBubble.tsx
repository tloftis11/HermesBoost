import type { ChatMessage } from "../types";

export function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`bubble-row ${message.role}`}>
      <div className="bubble-avatar">
        {isUser ? (
          "G"
        ) : (
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
            <path d="M10 3l1.4 4.6L16 9l-4.6 1.4L10 15l-1.4-4.6L4 9l4.6-1.4L10 3Z" fill="currentColor" />
          </svg>
        )}
      </div>
      <div className="bubble">{message.content}</div>
    </div>
  );
}
