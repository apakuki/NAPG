// Proxy to the agent's FastAPI read endpoint. Keeps the backend URL
// server-side so the browser only talks to localhost:3000, side-stepping
// CORS entirely. The backend address is read from NAPG_API_URL (default
// http://127.0.0.1:8000) — set this in .env.local when running the agent
// on a different host or port.

const BACKEND_URL = process.env.NAPG_API_URL ?? "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/status`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return Response.json(
        { error: `agent returned ${response.status}` },
        { status: 502 },
      );
    }
    const body = await response.json();
    return Response.json(body);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return Response.json(
      { error: `cannot reach agent at ${BACKEND_URL}: ${message}` },
      { status: 502 },
    );
  }
}
