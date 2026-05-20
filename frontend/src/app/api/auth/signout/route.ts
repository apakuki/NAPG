/**
 * POST /api/auth/signout — clears the `napg_session` cookie.
 *
 * No CSRF guard needed today (sign-out is idempotent and reduces privilege),
 * but the endpoint is POST-only on purpose so a stray `<a href>` cannot
 * trigger it from a cross-site context.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { clearSessionCookie } from "@/lib/session";

export async function POST() {
  const jar = await cookies();
  clearSessionCookie(jar);
  return NextResponse.json({ ok: true });
}
