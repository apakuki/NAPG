/**
 * POST /api/auth/signout — clears the `napg_session` cookie.
 *
 * Guarded by `applyGuards`: CSRF (Origin/Referer must match) + per-IP
 * rate limit. Sign-out is idempotent and only ever reduces privilege, so
 * the strict guard set is defence-in-depth, not a strict requirement.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { clearSessionCookie } from "@/lib/session";
import { applyGuards } from "@/lib/api-guards";

export async function POST(request: Request) {
  const blocked = applyGuards(request, { bucketName: "signout", csrf: true });
  if (blocked) return blocked;

  const jar = await cookies();
  clearSessionCookie(jar);
  return NextResponse.json({ ok: true });
}
