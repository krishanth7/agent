"""Broker connection API schemas.

WHAT MAY APPEAR IN THESE MODELS
-------------------------------
No token, ever. Not the JWT, not the refresh token, not the feed token, not the
API key, not the PIN, not the TOTP seed. `ApiModel` is `extra="forbid"`, so a
field that is not declared here cannot be smuggled into a response by a service
that passes an extra keyword — the request fails instead. That is the intended
behaviour: a validation error in development is a better outcome than a bearer
token in a browser's network tab.

The client code is a partial exception and is masked. It is an account
identifier rather than a credential (see `app.db.models.broker_account`), but
this API has no authentication in this phase, and an account identifier is still
half of what someone would need. Masking costs the dashboard nothing — an
operator with one account only needs to recognise it, not read it.

WHY THE CAPABILITY FLAGS ARE STATED RATHER THAN IMPLIED
-------------------------------------------------------
Same reasoning as `AgentStatusResponse`. "Can this thing place an order?" must
be answerable by reading a field, not by noticing that no endpoint exists to do
it. `order_placement_available` is typed `Literal[False]`, which means the
schema itself cannot express `True`: a future change that tried to advertise
order placement would fail to validate rather than quietly succeed.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from app.schemas.common import ApiModel


class BrokerStatusResponse(ApiModel):
    """Whether the broker integration is set up, and whether it is connected.

    THREE SEPARATE BOOLEANS, ON PURPOSE. `enabled`, `configured` and
    `connected` answer different questions and have different remedies:

    * not `enabled`    — the master switch is off; nothing has been attempted
    * not `configured` — a credential is missing from the environment
    * not `connected`  — set up, but no session has been established yet

    Collapsing them into one "broker: offline" would leave an operator unable to
    tell "I have not finished setting this up" from "my credentials were
    rejected", which are the two things they most need to distinguish.

    Produced without any network call. A status endpoint that could hang on a
    broker timeout is a status endpoint that stops working exactly when it is
    needed.
    """

    #: Which broker this describes. A string rather than an enum for the same
    #: reason the database column is: the vocabulary is open by design.
    broker: str

    enabled: bool
    configured: bool
    connected: bool

    #: Masked, and `None` when nothing is configured. See the module docstring.
    client_code: str | None = None

    #: When the current session lapses, or `None` when there is no session.
    #: Angel One publishes a policy rather than an expiry, so this is the next
    #: IST midnight — see `app.brokers.angel_one.auth`.
    session_expires_at: dt.datetime | None = None

    live_trading_enabled: bool
    paper_trading_enabled: bool

    #: Structurally false. There is no order-placement method on the adapter,
    #: no order route in the client, and no member on the broker Protocol.
    order_placement_available: Literal[False] = False


class BrokerConnectionTestResponse(ApiModel):
    """The result of a successful authenticate-and-read round trip.

    ONLY EVER RETURNED ON SUCCESS. A failure propagates as a `BrokerError`,
    which the existing handler renders in the standard error envelope with a
    status code that says what to do about it — 409 for "not configured", 502
    for "credentials rejected". Returning 200 with `connected: false` would
    make a rejected credential indistinguishable from a working one to anything
    that checks the status code, which is most things.

    That is why `connected` is `Literal[True]`: it is not a result field, it is
    a statement about what reaching this model means.
    """

    broker: str
    connected: Literal[True] = True

    #: Masked. See the module docstring.
    client_code: str

    #: The account holder as the broker reports it. `None` when the profile
    #: response omitted it, which is not an error.
    client_name: str | None = None

    #: Segments the account is enabled for. Carried because "your account is
    #: not enabled for NFO" is the most common cause of an authorization
    #: failure that otherwise looks inexplicable.
    exchanges: tuple[str, ...] = ()

    session_expires_at: dt.datetime

    #: When this check ran. Distinct from `session_expires_at`, and the reason a
    #: cached "connected" badge cannot pass itself off as a fresh one.
    checked_at: dt.datetime
