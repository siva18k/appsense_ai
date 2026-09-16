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
      <defs>
        <linearGradient id="appsense-mark-gradient" x1="16" y1="4" x2="16" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor="#b51d5b" />
          <stop offset="0.42" stopColor="#ee1740" />
          <stop offset="0.75" stopColor="#ff7418" />
          <stop offset="1" stopColor="#ffd8d8" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="#090a0d" />
      <path
        d="M4 4h24v8H12v16H4V4Z"
        fill="url(#appsense-mark-gradient)"
      />
    </svg>
  );
}
