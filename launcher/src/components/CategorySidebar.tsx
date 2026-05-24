import { Layers } from "lucide-react";
import type { CategoryGroup } from "../lib/appCatalog";

interface Props {
  groups: CategoryGroup[];
  selected: string;
  onSelect: (category: string) => void;
}

export function CategorySidebar({ groups, selected, onSelect }: Props) {
  return (
    <aside className="sidebar" aria-label="カテゴリ">
      <div className="sidebar-title">
        <Layers size={18} aria-hidden="true" />
        <span>カテゴリ</span>
      </div>
      <nav className="category-list">
        {groups.map((group) => (
          <section key={group.axis} className="category-group">
            {group.axis !== "all" && group.title ? <h3>{group.title}</h3> : null}
            {group.items.map((item) => (
              <button
                key={item.key}
                type="button"
                className={item.key === selected ? "category-button active" : "category-button"}
                onClick={() => onSelect(item.key)}
              >
                <span className="category-label">{item.label}</span>
                <span className="category-count" aria-label={`${item.label} ${item.count}件`}>
                  {item.count}
                </span>
              </button>
            ))}
          </section>
        ))}
      </nav>
    </aside>
  );
}

