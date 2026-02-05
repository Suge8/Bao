import { useI18n } from "@/i18n/i18n";
import { ChatLayout } from "./chat/layout";

export default function ChatPage() {
  const { t } = useI18n();
  return (
    <div className="flex h-full flex-col space-y-4" data-testid="page-chat">
      <div className="mx-auto w-full max-w-6xl">
        <div className="text-xl font-semibold">{t("page.chat.title")}</div>
      </div>
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col">
        <ChatLayout />
      </div>
    </div>
  );
}
