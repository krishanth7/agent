"""Broker-neutral error taxonomy.

Every failure that originates at a broker is translated into one of these
before it leaves `app.brokers`. Nothing above this layer should ever catch an
SDK exception, an `httpx` exception or a `KeyError` from a JSON payload — if it
has to, the adapter has failed at its job.

The taxonomy is organised around *what the caller should do about it*, which
is the only distinction that matters at a call site:

- `BrokerConfigurationError`  — nothing to do; the operator has not set it up
- `BrokerAuthenticationError` — the credentials are wrong; stop and tell someone
- `BrokerSessionExpiredError` — re-authenticate once, then continue
- `BrokerRateLimitError`      — back off and retry later
- `BrokerNetworkError`        — transient; a bounded retry is reasonable
- `BrokerDataError`           — the response was not what the contract says;
                                do not persist it, do not guess
- `BrokerUnavailableError`    — the broker is up but refusing service

Messages are written for an operator reading a log, and must never contain a
token, a PIN, a TOTP value or an API key.
"""

from __future__ import annotations

from app.core.exceptions import AppError


class BrokerError(AppError):
    """Base class for every broker failure.

    Inherits `AppError` so the existing exception handler renders it in the
    standard envelope with no new wiring. 502 rather than 500 is the honest
    status: the request reached us and we did our part, but an upstream
    dependency did not hold up its end.
    """

    code = "BROKER_ERROR"
    status_code = 502
    message = "The broker request could not be completed."

    def __init__(self, message: str | None = None) -> None:
        """Fall back to the class's own message when none is supplied.

        `AppError` requires a message. Most broker failures have nothing useful
        to add beyond their type — there is exactly one thing worth saying
        about a rate limit — and forcing every raise site to restate it would
        guarantee that the wording drifts between them. Passing a message
        remains possible for the cases that genuinely have detail to add, such
        as naming the route that failed.
        """
        super().__init__(message if message is not None else type(self).message)


class BrokerConfigurationError(BrokerError):
    """No usable credentials, or the integration is switched off.

    409 rather than 5xx: nothing is broken. The operator has not finished
    configuring the system, and no amount of retrying will change that.
    """

    code = "BROKER_NOT_CONFIGURED"
    status_code = 409
    message = "Angel One is not configured. Set the credentials and enable it."


class BrokerAuthenticationError(BrokerError):
    """The broker rejected the credentials.

    Deliberately does not distinguish a wrong PIN from a wrong TOTP from a
    blocked account. That distinction is useful to an attacker enumerating
    credentials and useless to an operator, who has to check all three anyway.
    The specific broker error code is logged server-side.
    """

    code = "BROKER_AUTHENTICATION_FAILED"
    status_code = 502
    message = "Angel One rejected the credentials."


class BrokerSessionExpiredError(BrokerError):
    """The session was valid and no longer is.

    Separate from `BrokerAuthenticationError` because the correct response is
    different: this one is recoverable by refreshing, and the credentials are
    not in question. Angel One sessions expire at midnight IST regardless of
    activity, so this is an expected daily event, not an incident.
    """

    code = "BROKER_SESSION_EXPIRED"
    status_code = 502
    message = "The Angel One session has expired."


class BrokerAuthorizationError(BrokerError):
    """Authenticated, but not permitted to do this.

    Typically a product or segment the account is not enabled for.
    """

    code = "BROKER_NOT_AUTHORIZED"
    status_code = 502
    message = "The Angel One account is not permitted to perform this action."


class BrokerRateLimitError(BrokerError):
    """Too many requests.

    429 is passed through so a caller can distinguish "slow down" from "this
    is broken" without parsing a message string.
    """

    code = "BROKER_RATE_LIMITED"
    status_code = 429
    message = "Angel One rate limit exceeded. Retry after a short delay."


class BrokerNetworkError(BrokerError):
    """The request never got a usable answer — timeout, DNS, refused socket."""

    code = "BROKER_UNREACHABLE"
    status_code = 504
    message = "Angel One could not be reached."


class BrokerDataError(BrokerError):
    """A response arrived but did not match the documented contract.

    This is the important one. It fires when a field is missing, unparseable,
    or fails a sanity rule — and it deliberately fails the whole request
    instead of substituting a zero or a `None`. A silently defaulted price is
    indistinguishable from a real one downstream, and by the time anyone
    notices it is already in the database.
    """

    code = "BROKER_DATA_ERROR"
    status_code = 502
    message = "Angel One returned data that could not be interpreted."


class BrokerUnavailableError(BrokerError):
    """The broker is reachable but not serving — maintenance, 5xx, outage."""

    code = "BROKER_UNAVAILABLE"
    status_code = 503
    message = "Angel One is currently unavailable."
