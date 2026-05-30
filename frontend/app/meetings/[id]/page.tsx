import Link from "next/link";
import { notFound } from "next/navigation";

import { MeetingDetail } from "../../../components/MeetingDetail";
import { fetchMeeting, MeetingNotFoundError } from "../../../lib/api";

export default async function MeetingDetailPage({ params }: { params: { id: string } }) {
  try {
    const meeting = await fetchMeeting(params.id);

    return (
      <main className="detail-page">
        <Link href="/" className="back-link">
          返回工作台
        </Link>
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
