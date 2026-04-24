import { Layers } from "lucide-react";

interface Props {
  categories: string[];
  selected: string;
  onSelect: (category: string) => void;
}

export function CategorySidebar({ categories, selected, onSelect }: Props) {
  return (
    <aside className="sidebar" aria-label="カテゴリ">
      <div className="sidebar-title">
        <Layers size={18} aria-hidden="true" />
        <span>カテゴリ</span>
      </div>
      <nav className="category-list">
        {categories.map((category) => (
          <button
            key={category}
            type="button"
            className={category === selected ? "category-button active" : "category-button"}
            onClick={() => onSelect(category)}
          >
            {category}
          </button>
        ))}
      </nav>
    </aside>
  );
}

