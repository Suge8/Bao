import { ChatLayout } from "./chat/layout";

export default function ChatPage() {
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden" data-testid="page-chat">
      <div className="mx-auto flex min-h-0 min-w-0 w-full max-w-[1400px] flex-1 flex-col overflow-hidden">
        <ChatLayout />
      </div>
    </div>
  );
}
