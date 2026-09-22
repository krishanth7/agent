import type { MarketStatus } from "@/types/trading";

/**
 * The last frontend-owned mock value.
 *
 * Everything else that used to live here — the account summary, the session
 * journal, the default target and the pinned "today" — now comes from the
 * backend over `/api/v1`. They were deleted rather than left in place: a
 * second copy of the numbers would eventually disagree with the API, and a
 * fallback that silently substitutes plausible figures is exactly the failure
 * mode this dashboard must not have.
 *
 * Market status stays here because Phase 2 exposes no exchange-session
 * endpoint. It is a static label, not a figure anyone would trade against.
 * It belongs to an exchange session/holiday service in a later phase.
 */
export const MOCK_MARKET_STATUS: MarketStatus = "closed";
