import { useI18n } from "@/i18n/i18n";
import { ChatLayout } from "./chat/layout";

export default function ChatPage() {
  const { t } = useI18n();
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden" data-testid="page-chat">
      <div className="mx-auto min-w-0 w-full max-w-[1400px]">
        <div className="px-1">
           <h1 className="text-xl font-bold tracking-tight text-foreground">{t("page.chat.title")}</h1>
        </div>
      </div>
      <div className="mx-auto flex min-h-0 min-w-0 w-full max-w-[1400px] flex-1 flex-col overflow-hidden">
        <ChatLayout />
      </div>
    </div>
  );
}
