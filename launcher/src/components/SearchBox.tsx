import { Search, X } from "lucide-react";

interface Props {
  value: string;
  onChange: (value: string) => void;
}

export function SearchBox({ value, onChange }: Props) {
  return (
    <label className="search-box" aria-label="アプリを検索">
      <Search size={20} aria-hidden="true" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="アプリ名、用途、キーワードで検索"
      />
      {value ? (
        <button className="icon-button" type="button" onClick={() => onChange("")} title="検索をクリア">
          <X size={18} aria-hidden="true" />
        </button>
      ) : null}
    </label>
  );
}

