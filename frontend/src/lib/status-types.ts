// Shape mirrors napg.api.StatusResponse. Keep in sync with agent/napg/api.py.

export type CardError = { error: string };

export type HeartbeatCard = {
  rpc_url: string;
  chain_id: number;
  latency_ms: number;
  block: {
    number: number;
    hash: string;
    parent_hash: string;
    timestamp: number;
  };
  reorg_detected: boolean;
  observed_at: number;
};

export type AerodromeCard = {
  chain_id: number;
  sell_token: string;
  buy_token: string;
  sell_amount: number;
  buy_amount: number;
  liquidity_available: boolean;
  quoted_rate: number | null;
  peg_deviation_bps: number | null;
  sources: string[];
  block_number: number | null;
  latency_ms: number;
  observed_at: number;
};

export type MorphoMarket = {
  label: string;
  market_id: string;
  loan_symbol: string;
  collateral_symbol: string;
  total_supply_assets: number;
  total_borrow_assets: number;
  utilization_bps: number;
  last_update: number;
  staleness_seconds: number;
  block_number: number;
  observed_at: number;
};

export type MorphoCard = {
  chain_id: number;
  block_number: number;
  block_timestamp: number;
  markets: MorphoMarket[];
  latency_ms: number;
  observed_at: number;
};

export type StatusResponse = {
  heartbeat: HeartbeatCard | CardError;
  aerodrome: AerodromeCard | CardError;
  morpho: MorphoCard | CardError;
};

export function isCardError(card: object): card is CardError {
  return "error" in card && typeof (card as CardError).error === "string";
}
