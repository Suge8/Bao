export function Page({ title, description }: { title: string; description: string }) {
  return (
    <div className="mx-auto w-full max-w-5xl">
      <div className="text-xl font-semibold">{title}</div>
      <div className="mt-2 text-sm text-muted-foreground">{description}</div>

      <div className="mt-6 rounded-2xl bg-foreground/5 p-4">
        <div className="text-xs text-muted-foreground">Stage 0 骨架：此页面仅占位。</div>
      </div>
    </div>
  );
}
