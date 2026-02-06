export function Page({ title, description }: { title: string; description: string }) {
  return (
    <div className="mx-auto w-full max-w-5xl">
      <div className="text-xl font-semibold">{title}</div>
      <div className="mt-2 text-sm text-muted-foreground">{description}</div>
    </div>
  );
}
