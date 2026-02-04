import { Globe } from "@/components/ui/globe";

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-5xl p-6">
        <h1 className="text-2xl font-semibold">Bao Desktop</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Tailwind v4 + shadcn + Magic UI (Globe) smoke test
        </p>

        <div className="mt-6 rounded-xl border p-4">
          <Globe />
        </div>
      </div>
    </div>
  );
}
