"""Shared schema building blocks.

MONEY SERIALIZATION POLICY
--------------------------
Monetary values are `Decimal` everywhere inside the application and are
quantized to two decimal places (paise) before they reach a schema. On the
wire they are emitted as **JSON numbers**, not strings, so the frontend can
consume them without a parse step.

JSON has no concept of a trailing zero: `25000.00` and `25000.0` are the same
number, and the exact byte sequence is decided by the encoder. What matters —
and what the test suite asserts — is that no binary floating-point artifact
(`25000.000000000004`) can ever appear. Quantizing to paise before encoding
guarantees that, because every such value is exactly representable.

Display formatting to two decimals is the presentation layer's job; the
frontend already does it via `Intl.NumberFormat`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.core.constants import CURRENCY
from app.domain.enums import DataSource


def _to_json_number(value: Decimal) -> float:
    """Render a quantized `Decimal` as a JSON number.

    Pydantic v2 serializes `Decimal` to a *string* by default, to preserve
    precision that JSON cannot express. That is the right default in general
    and the wrong one here: these values are already quantized to paise, and
    forcing every consumer to parse `"25000.00"` before arithmetic is a worse
    trade than the precision guarantee buys.

    The conversion is safe because of the quantization. Amounts bounded by
    ₹10 crore with at most two decimal places are all exactly representable as
    IEEE-754 doubles, so no artifact can be introduced here.
    """
    return float(value)


#: Applied at the JSON boundary only. Internal `model_dump()` keeps `Decimal`,
#: so service-to-service use and tests retain exact arithmetic.
_JsonNumber = PlainSerializer(_to_json_number, return_type=float, when_used="json")

#: A monetary amount that may be negative (realized P&L can be a loss).
Money = Annotated[Decimal, Field(decimal_places=2), _JsonNumber]

#: A monetary amount that can never be negative (balances, margin, targets).
NonNegativeMoney = Annotated[Decimal, Field(ge=0, decimal_places=2), _JsonNumber]

#: An uncapped percentage. Progress may legitimately exceed 100.
Percentage = Annotated[Decimal, Field(decimal_places=2), _JsonNumber]

CurrencyCode = Literal["INR"]


class ApiModel(BaseModel):
    """Base for every response schema.

    `use_enum_values` is deliberately *not* set: enums serialize by value
    anyway, and keeping the members typed makes service code far easier to
    reason about.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class CurrencyMixin(BaseModel):
    """Every monetary payload states its currency explicitly."""

    currency: CurrencyCode = CURRENCY


class SourcedMixin(BaseModel):
    """Marks where a payload's figures came from.

    Present so a client can visibly distinguish demo data from real account
    data. Once a broker is connected this becomes a safety-critical field: a
    mock number must never be able to render as though it were live.
    """

    source: DataSource = DataSource.MOCK


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """The single error envelope every failure is rendered into."""

    error: ErrorDetail
