"use client";

export function Field({
  label,
  value,
  onChange,
  placeholder,
  className = "",
  required = false,
  error = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  required?: boolean;
  error?: boolean;
}) {
  return (
    <div className={className}>
      <label className="field-label !mb-1.5 !text-xs">
        {label}
        {required ? <span className="text-[var(--danger)]"> *</span> : null}
      </label>
      <input
        type="text"
        className={`field-input !text-[13px] ${error ? "field-invalid" : ""}`}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error || undefined}
        aria-required={required || undefined}
      />
      {error && <p className="field-error">请填写{label}</p>}
    </div>
  );
}
