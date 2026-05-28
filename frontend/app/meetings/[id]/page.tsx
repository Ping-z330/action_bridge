import Link from "next/link";

import { MeetingDetail } from "../../../components/MeetingDetail";
import { fetchMeeting } from "../../../lib/api";

export default async function MeetingDetailPage({ params }: { params: { id: string } }) {
  const meeting = await fetchMeeting(params.id);

  return (
    <main className="grid">
      <Link href="/">返回首页</Link>
      <MeetingDetail meeting={meeting} />
    </main>
  );
}
