"use client";

import { buildComposeIntentUrl } from "@/lib/manifest";

interface Props {
  /** Cast body. Truncated to 280 chars by `buildComposeIntentUrl`. */
  text: string;
  /**
   * Page URL the Farcaster client will embed below the cast. Should be an
   * absolute URL that resolves to a page exposing an `fc:miniapp` meta tag,
   * otherwise the embed renders as a generic OG-image card instead of a
   * launch-frame button.
   */
  embedUrl: string;
  className?: string;
}

/**
 * Opens the Farcaster compose-intent URL in a new tab. The Farcaster client
 * (web or mobile) pre-fills a new cast with the supplied text + embed, and
 * the user reviews + posts manually -- we never sign anything on their
 * behalf, so no Farcaster API key, no signer, no audit trail required.
 *
 * Deliberately a plain anchor with `target="_blank"`: the in-app browser
 * pops a new webview at farcaster.xyz/~/compose where the user is already
 * authenticated. window.open() with a non-noopener policy would be
 * marginally fancier but doesn't change the UX in practice.
 */
export function ShareToFarcaster({ text, embedUrl, className }: Props) {
  const href = buildComposeIntentUrl(text, embedUrl);
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={
        className ??
        "tap inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 px-3 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
      }
    >
      <span aria-hidden>↗</span>
      Share to Farcaster
    </a>
  );
}
