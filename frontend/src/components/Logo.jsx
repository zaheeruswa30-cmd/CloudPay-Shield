/** CloudPay Shield mark: a shield whose inner line is a linked chain of blocks (the hash-chained ledger). */
export function LogoMark({ size = 28, className = "" }) {
  return (
    <svg className={`logo-mark ${className}`} width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" fill="none">
      <path d="M16 2.5 4.5 6.8v8.4c0 7 4.8 12.6 11.5 14.3 6.7-1.7 11.5-7.3 11.5-14.3V6.8L16 2.5Z"
        stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <rect x="9" y="13" width="4.4" height="4.4" rx="1" fill="currentColor" />
      <rect x="18.6" y="13" width="4.4" height="4.4" rx="1" fill="currentColor" opacity=".55" />
      <path d="M13.4 15.2h5.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M16 20.5v2.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" opacity=".55" />
    </svg>
  );
}

export function Logo({ size = 28, sub }) {
  return (
    <span className="logo" aria-label="CloudPay Shield">
      <LogoMark size={size} />
      <span className="logo-text">
        <strong>CloudPay<span className="accent-text"> Shield</span></strong>
        {sub && <span className="tiny muted">{sub}</span>}
      </span>
    </span>
  );
}
