import Link from "next/link";
import { notFound } from "next/navigation";

import { MeetingDetail } from "../../../components/MeetingDetail";
import { fetchMeeting, MeetingNotFoundError } from "../../../lib/api";

export default async function MeetingDetailPage({ params }: { params: { id: string } }) {
  try {
    const meeting = await fetchMeeting(params.id);

    return (
      <main className="grid">
        <Link href="/">返回首页</Link>
        <MeetingDetail meeting={meeting} />
      </main>
    );
  } catch (error) {
    if (error instanceof MeetingNotFoundError) {
      notFound();
    }

    throw error;
  }
}
