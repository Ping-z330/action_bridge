import { AppShell } from "../../components/AppShell";
import { HistoryRecords } from "../../components/HistoryRecords";
import { fetchActionItems, fetchMeetings } from "../../lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function HistoryPage() {
  const meetings = await fetchMeetings().catch(() => []);
  const actionItems = await fetchActionItems().catch(() => []);

  return (
    <AppShell active="history">
      <HistoryRecords meetings={meetings} actionItems={actionItems} />
    </AppShell>
  );
}
