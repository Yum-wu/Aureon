import { useTranslation } from "react-i18next";
import { useChat } from "../hooks/useChat";
import { MessageList } from "./MessageList";
import { InputArea } from "./InputArea";

/** Main chat window \u2014 combines header, error toast, message list, and input area */
export function ChatWindow() {
  const { t } = useTranslation();
  const {
    messages,
    isLoading,
    error,
    sendMessage,
    clearChat,
    stopGeneration,
    clearError,
  } = useChat();

  const hasMessages = messages.length > 0;

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <header className="flex items-center justify-between bg-[var(--bg-secondary)] border-b border-[var(--border)] px-6 py-3">
        <h1 className="text-lg font-semibold text-[var(--text-primary)]">
          <span role="img" aria-label="robot">\ud83e\udd16</span> {t("chat.title")}
        </h1>
        <button
          onClick={clearChat}
          className="text-sm text-[var(--text-tertiary)] hover:text-[var(--error)] transition-colors px-3 py-1 rounded-lg hover:bg-red-500/10"
        >
          {t("chat.clear")}
        </button>
      </header>

      {error && (
        <div className="bg-red-500/10 border-b border-red-500/30 px-6 py-2 text-sm text-red-400 flex items-center justify-between">
          <span>\u26a0\ufe0f {error}</span>
          <button
            onClick={clearError}
            className="text-red-400 hover:text-red-300"
          >
            \u2715
          </button>
        </div>
      )}

      {hasMessages ? (
        <MessageList messages={messages} isLoading={isLoading} />
      ) : (
        <div className="flex-1 flex items-center justify-center text-[var(--text-tertiary)]">
          <div className="text-center px-4">
            <div className="text-5xl mb-4" role="img" aria-label="chat">\ud83d\udcac</div>
            <p className="text-base font-medium text-[var(--text-secondary)]">{t("chat.emptyTitle")}</p>
            <p className="text-sm mt-1 text-[var(--text-tertiary)]">{t("chat.emptySubtitle")}</p>
            <p className="text-xs mt-2 text-[var(--text-tertiary)] max-w-xs mx-auto opacity-60">{t("chat.emptyHint")}</p>
          </div>
        </div>
      )}

      <InputArea
        onSend={sendMessage}
        isLoading={isLoading}
        onStop={stopGeneration}
      />
    </div>
  );
}
