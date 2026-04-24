import type { ToolApp } from "../lib/types";
import { AppCard } from "./AppCard";
import { EmptyState } from "./EmptyState";

interface Props {
  apps: ToolApp[];
  onLaunch: (app: ToolApp) => void;
  onDetail: (app: ToolApp) => void;
  isFiltered: boolean;
}

export function AppGrid({ apps, onLaunch, onDetail, isFiltered }: Props) {
  if (apps.length === 0) {
    return (
      <EmptyState
        title={isFiltered ? "該当するアプリがありません" : "登録されているアプリがありません"}
        message={isFiltered ? "検索条件またはカテゴリを変更してください。" : "appsフォルダにアプリを追加すると表示されます。"}
      />
    );
  }

  return (
    <section className="app-grid" aria-label="アプリ一覧">
      {apps.map((app) => (
        <AppCard key={app.id} app={app} onLaunch={onLaunch} onDetail={onDetail} />
      ))}
    </section>
  );
}

