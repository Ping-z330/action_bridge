import { AppShell } from "../../components/AppShell";
import { TaskResults } from "../../components/TaskResults";
import { fetchActionItems } from "../../lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function TasksPage() {
  const actionItems = await fetchActionItems().catch(() => []);

  return (
    <AppShell active="tasks">
      <TaskResults initialItems={actionItems} />
    </AppShell>
  );
}
