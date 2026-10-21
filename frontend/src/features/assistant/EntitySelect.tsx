import { useEffect, useState } from "react";

export const CUSTOM = "__custom__";

export interface SelectOption {
  value: string;
  label?: string;
}

interface EntitySelectProps {
  id: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  className: string;
  /** Offer "custom…" with a text box, for values the incident doesn't name. */
  allowCustom?: boolean;
  customPlaceholder?: string;
}

/**
 * A dropdown of the incident's entities, with an optional "custom…" escape hatch. Entity names and
 * IDs are machine-emitted, so options render monospace (frontend conventions).
 */
export default function EntitySelect({
  id,
  value,
  options,
  onChange,
  className,
  allowCustom = true,
  customPlaceholder = "type a value",
}: EntitySelectProps) {
  const known = options.some((o) => o.value === value);
  const [custom, setCustom] = useState(!known && value !== "");
  const showCustom = allowCustom && (custom || (!known && value !== ""));
  useEffect(() => {
    if (known && value !== "") setCustom(false); // picked (or reset to) a listed value
  }, [known, value]);

  return (
    <div className="space-y-1.5">
      <select
        id={id}
        value={showCustom ? CUSTOM : value}
        onChange={(e) => {
          if (e.target.value === CUSTOM) {
            setCustom(true);
            onChange("");
          } else {
            setCustom(false);
            onChange(e.target.value);
          }
        }}
        className={className}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label ?? o.value}
          </option>
        ))}
        {allowCustom && <option value={CUSTOM}>custom…</option>}
      </select>
      {showCustom && (
        <input
          id={`${id}-custom`}
          aria-label={`${id} custom value`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={customPlaceholder}
          className={className}
          autoFocus
        />
      )}
    </div>
  );
}
