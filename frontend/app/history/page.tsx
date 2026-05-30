import { AppShell } from "../../components/AppShell";
import { HistoryRecords } from "../../components/HistoryRecords";
import { fetchMeetings } from "../../lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function HistoryPage() {
  const meetings = await fetchMeetings().catch(() => []);

  return (
    <AppShell active="history">
      <HistoryRecords meetings={meetings} />
    </AppShell>
  );
}
