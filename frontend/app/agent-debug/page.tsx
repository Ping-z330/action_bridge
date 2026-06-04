import { AgentDebugPanel } from "../../components/AgentDebugPanel";
import { AppShell } from "../../components/AppShell";
import { fetchAgentTraces } from "../../lib/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function AgentDebugPage() {
  const traces = await fetchAgentTraces().catch(() => []);

  return (
    <AppShell active="agent-debug">
      <AgentDebugPanel traces={traces} />
    </AppShell>
  );
}
