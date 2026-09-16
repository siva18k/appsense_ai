type BrandMarkProps = {
  size?: number;
  className?: string;
};

export function BrandMark({ size = 34, className = "brand-mark" }: BrandMarkProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden
    >
      <rect width="32" height="32" rx="9" fill="#2a2421" />
      <circle cx="16" cy="16" r="7.2" stroke="#c96442" strokeWidth="2" />
      <circle cx="16" cy="16" r="3.4" fill="#c96442" />
    </svg>
  );
}
