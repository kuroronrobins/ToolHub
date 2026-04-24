import { Inbox } from "lucide-react";

interface Props {
  title: string;
  message: string;
}

export function EmptyState({ title, message }: Props) {
  return (
    <section className="empty-state" role="status">
      <Inbox size={36} aria-hidden="true" />
      <h2>{title}</h2>
      <p>{message}</p>
    </section>
  );
}

