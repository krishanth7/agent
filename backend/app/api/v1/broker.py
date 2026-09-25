"""Broker connection routes.

TWO ENDPOINTS, BOTH GET, NEITHER OF THEM A CONTROL SURFACE
----------------------------------------------------------
There is no route here to place, modify, cancel or square off anything. There is
also no route to *configure* the broker: credentials come from the environment,
and an endpoint that could set them would move the most sensitive values in the
system onto an unauthenticated HTTP surface.

WHY THE CONNECTION TEST IS A GET
-------------------------------
It authenticates, which is a side effect at the broker, and the reflex is to
make that a POST. Two things argue the other way, and the second is decisive.

First, the session is cached: `authenticate` returns the existing session
without a network call when one is live, so repeated calls do not mean repeated
logins. The expensive path runs at most once a day per process.

Second, this API's CORS policy allows `GET`, `PUT` and `OPTIONS` and not `POST`.
Adding `POST` to serve a read-only diagnostic would widen the write surface of
the entire API in a phase whose whole point is that nothing writes. A narrower
CORS policy is worth more than the HTTP-semantics purity of one endpoint.

WHY STATUS AND TEST ARE SEPARATE
--------------------------------
`/status` answers from configuration and process state and cannot fail, hang or
touch the network. `/connection-test` talks to the broker and can do all three.
A dashboard polls the first and offers the second as a deliberate action; one
endpoint doing both would mean every poll of a status badge fires a request at
Angel One.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import BrokerServiceDep
from app.schemas.broker import BrokerConnectionTestResponse, BrokerStatusResponse

router = APIRouter(prefix="/broker", tags=["broker"])


@router.get(
    "/status",
    response_model=BrokerStatusResponse,
    summary="Broker configuration and session state",
)
async def read_broker_status(service: BrokerServiceDep) -> BrokerStatusResponse:
    """Report whether the broker is enabled, configured and connected.

    Always 200. "Not configured" is a fact about this deployment, not a failure
    of this request, and returning an error for it would make a fresh install
    look broken.
    """
    return await service.get_status()


@router.get(
    "/connection-test",
    response_model=BrokerConnectionTestResponse,
    summary="Authenticate against the broker and read the account profile",
    responses={
        409: {"description": "Angel One is not configured or not enabled."},
        502: {"description": "The broker rejected the credentials or the response."},
        503: {"description": "The broker is reachable but not serving."},
        504: {"description": "The broker could not be reached."},
    },
)
async def test_broker_connection(
    service: BrokerServiceDep,
) -> BrokerConnectionTestResponse:
    """Prove this deployment can reach and read the configured account.

    Failures are raised, not reported in the body — see
    `BrokerConnectionTestResponse` for why a 200 with `connected: false` would
    be the more dangerous design. The status code distinguishes the remedies:
    409 means set the credentials, 502 means they were refused.
    """
    return await service.test_connection()
