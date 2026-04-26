import type { ReactNode } from "react";

interface Props {
  title: string;
  summary?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function AppStudioCollapsibleSection({ title, summary, defaultOpen = false, children }: Props) {
  return (
    <details className="studio-collapsible" open={defaultOpen}>
      <summary>
        <span>{title}</span>
        {summary ? <small>{summary}</small> : null}
      </summary>
      <div className="studio-collapsible-body">{children}</div>
    </details>
  );
}
