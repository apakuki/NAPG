/**
 * Proxy to the agent's GET /api/audit/breaches. Same pattern as
 * /api/status: backend URL stays server-side, browser only talks to the
 * Next host so CORS never enters the picture.
 *
 * Query params (`source`, `limit`) are forwarded verbatim; the backend
 * clamps `limit` to [1, 200] via FastAPI's Query validator and 422s
 * out-of-range values. We do not re-validate here -- if the agent rejects
 * the request we surface its status.
 */

import { NextResponse, type NextRequest } from "next/server";

const BACKEND_URL = process.env.NAPG_API_URL ?? "http://127.0.0.1:8000";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const params = new URLSearchParams();
  const limit = request.nextUrl.searchParams.get("limit");
  const source = request.nextUrl.searchParams.get("source");
  if (limit) params.set("limit", limit);
  if (source) params.set("source", source);
  const qs = params.toString();
  const url = `${BACKEND_URL}/api/audit/breaches${qs ? `?${qs}` : ""}`;
  try {
    const response = await fetch(url, { cache: "no-store" });
    const body = await response.json();
    if (!response.ok) {
      return NextResponse.json(body, { status: response.status });
    }
    return NextResponse.json(body);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: `cannot reach agent at ${BACKEND_URL}: ${message}` },
      { status: 502 },
    );
  }
}
