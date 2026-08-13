export default function GlobalLoading() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-ink-muted">
      <span className="icon-badge icon-badge-brand">
        <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
      </span>
      <p className="text-[13px]">加载中…</p>
    </div>
  );
}
