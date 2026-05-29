export default function SkeletonCard() {
  return (
    <div className="skeleton-card" data-testid="skeleton-card" aria-hidden="true">
      <div className="skeleton-block meta" />
      <div className="skeleton-block title" />
      <div className="skeleton-block line" />
      <div className="skeleton-block line" />
      <div className="skeleton-block line short" />
    </div>
  )
}
