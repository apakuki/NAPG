/**
 * GET /api/auth/siwf/poll?token=XYZ — checks the Farcaster relay for the
 * sign-in state of a previously opened channel. On `completed`, verifies the
 * signature server-side (never trusts the client's fid claim, per Phase 3
 * security baseline) and sets the `napg_session` cookie. The browser then
 * reloads to pick up the signed-in state.
 *
 * Response shapes:
 *   - `{ state: "pending" }` while the user hasn't completed in-app yet
 *   - `{ state: "completed", fid }` once the session cookie is set
 *   - `{ state: "verification_failed", reason }` if the relay returned a
 *     signature that fails verification
 *   - `{ state: "unknown" }` if the token was never issued or has expired
 *     (channels self-purge after 5 minutes)
 *
 * Status is always HTTP 200 — the discriminator lives in the body so the
 * client doesn't have to differentiate "real network error" from "channel
 * still pending" via status code.
 *
 * Guarded by `applyGuards` for the rate limit (GET, no CSRF check). A 1.5 s
 * client poll for up to 5 min => ~200 polls per session; the bucket caps
 * at 60/burst refilling at 4/s, which exactly matches that envelope and
 * cuts off an attacker probing channel tokens at scale.
 */

import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

import { setSessionCookie } from "@/lib/session";
import { pollChannel } from "@/lib/siwf";
import { applyGuards } from "@/lib/api-guards";

export async function GET(request: NextRequest) {
  const blocked = applyGuards(request, {
    bucketName: "siwf_poll",
    csrf: false,
  });
  if (blocked) return blocked;

  const token = request.nextUrl.searchParams.get("token");
  if (!token) {
    return NextResponse.json(
      { state: "unknown", error: "missing token" },
      { status: 400 },
    );
  }

  const result = await pollChannel(token);

  if (result.state === "completed") {
    setSessionCookie(await cookies(), result.fid, result.address);
  }

  return NextResponse.json(result);
}
