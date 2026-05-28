import { MeetingForm } from "../components/MeetingForm";
import { MeetingList } from "../components/MeetingList";
import { fetchMeetings } from "../lib/api";

export default async function HomePage() {
  const meetings = await fetchMeetings().catch(() => []);

  return (
    <main className="grid two">
      <section className="stack">
        <span className="pill">ActionBridge</span>
        <h1>把会议内容，变成可执行事项。</h1>
        <p>从一段会议记录开始，自动生成摘要、结论和行动项，并保留足够清晰的结构，方便同步到团队协作工具。</p>
        <MeetingForm />
      </section>
      <MeetingList meetings={meetings} />
    </main>
  );
}
