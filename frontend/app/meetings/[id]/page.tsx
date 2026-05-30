import Link from "next/link";
import { notFound } from "next/navigation";

import { MeetingDetail } from "../../../components/MeetingDetail";
import { fetchMeeting, MeetingNotFoundError } from "../../../lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function MeetingDetailPage({ params }: { params: { id: string } }) {
  try {
    const meeting = await fetchMeeting(params.id);

    return (
      <main className="detail-page">
        <Link href={`/?meetingId=${params.id}`} className="back-link" prefetch={false}>
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
