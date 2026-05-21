/**
 * Pure-logic summary of an EIP-5792 `wallet_getCapabilities` response.
 *
 * The full schema is open-ended (each wallet may return arbitrary extra keys),
 * but for Phase 3 we only care about two flags:
 *   - batch:     `atomic.status` is `supported` or `ready`. Both mean the
 *                wallet can execute multiple calls in one user operation.
 *                `unsupported` is the negative.
 *   - paymaster: `paymasterService.supported === true`. The wallet is
 *                willing to consume an ERC-7677 paymaster URL we provide.
 *
 * Anything else (missing keys, malformed shape) is treated as "not supported"
 * rather than thrown. The UI then renders a degraded state and we move on.
 *
 * Spec: https://eips.ethereum.org/EIPS/eip-5792
 */

export interface CapabilitySummary {
  batch: boolean;
  paymaster: boolean;
}

interface AtomicCapability {
  status?: "supported" | "ready" | "unsupported";
}

interface PaymasterCapability {
  supported?: boolean;
}

export interface RawCapabilities {
  atomic?: AtomicCapability;
  paymasterService?: PaymasterCapability;
  // Pass-through: wallets may add arbitrary extras and we ignore them.
  [key: string]: unknown;
}

export function summarizeCapabilities(
  caps: RawCapabilities | null | undefined,
): CapabilitySummary {
  if (!caps || typeof caps !== "object") {
    return { batch: false, paymaster: false };
  }
  const atomic = caps.atomic?.status;
  const batch = atomic === "supported" || atomic === "ready";
  const paymaster = caps.paymasterService?.supported === true;
  return { batch, paymaster };
}
