/**
 * GET /api/auth/session — returns the current session (fid + exp) if the
 * caller carries a valid `napg_session` cookie, or `{ authenticated: false }`
 * otherwise. Client uses this to render signed-in state without trusting any
 * local storage.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getSessionFromCookies } from "@/lib/session";

export async function GET() {
  const session = getSessionFromCookies(await cookies());
  if (!session) {
    return NextResponse.json({ authenticated: false });
  }
  return NextResponse.json({
    authenticated: true,
    fid: session.fid,
    exp: session.exp,
  });
}
