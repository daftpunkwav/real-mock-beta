"use client";

/** 面试配置页基础本地组件：Select / 按钮组 / 无简历提示。 */

export function Select({
  label,
  value,
  options,
  labels,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  labels?: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="field-label !mb-1 !text-xs">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="field-select !h-9 !text-xs"
      >
        {options.map((o, i) => (
          <option key={o} value={o}>
            {labels?.[i] || o}
          </option>
        ))}
      </select>
    </div>
  );
}

/** 标签选择按钮组（公司/性格）：选中项高亮。 */
export function ChoiceGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label?: string;
  value: T;
  options: { id: T; name: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div>
      {label && <label className="field-label !mb-2 !text-xs">{label}</label>}
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const selected = value === o.id;
          return (
            <button
              key={o.id}
              type="button"
              onClick={() => onChange(o.id)}
              className={`rounded-md border px-3 py-1.5 text-[12px] font-medium transition-all duration-base ease-google active:scale-[0.98] ${
                selected
                  ? "border-[var(--primary)] bg-[var(--info-soft)] text-[var(--info-ink)] shadow-focus"
                  : "border-surface-border bg-surface-card text-ink-muted hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-[var(--info-ink)]"
              }`}
            >
              {o.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** 公司选择按钮网格（紧凑多列）。 */
export function CompanyGrid<T extends string>({
  value,
  companies,
  onChange,
}: {
  value: T;
  companies: { id: T; name: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4 md:grid-cols-7">
      {companies.map((c) => {
        const selected = value === c.id;
        return (
          <button
            key={c.id}
            type="button"
            onClick={() => onChange(c.id)}
            className={`rounded-md border px-2 py-2 text-center text-[12px] font-medium transition-all duration-base ease-google active:scale-[0.98] ${
              selected
                ? "border-[var(--primary)] bg-[var(--info-soft)] text-[var(--info-ink)] shadow-focus"
                : "border-surface-border bg-surface-card text-ink-muted hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-[var(--info-ink)]"
            }`}
          >
            {c.name}
          </button>
        );
      })}
    </div>
  );
}

/** 无简历时的提示块（warning 文案原样）。 */
export function ResumeWarning() {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-ink-muted">关联简历</label>
      <p className="rounded-md border border-[var(--warning)]/30 bg-[var(--warning-soft)] px-2.5 py-2 text-[11px] text-[var(--warning-ink)]">
        暂无简历,可稍后在「简历管理」上传
      </p>
    </div>
  );
}
