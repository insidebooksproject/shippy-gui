"""Shared label journal glue: label status tracking.

The journal itself lives in ibp-printing and is shared by every IBP app on the
machine, so a label bought in shippy (CLI) is seen here too. Its calls never
raise for journal problems; the wrappers below additionally make sure a
journal hiccup can never break shipping (anything unexpected is logged and
ignored).
"""

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
import time
from typing import Any, Optional

import ibp_printing

from shippy_gui.core.models import AddressBase

logger = logging.getLogger(__name__)

APP_NAME = "shippy-gui"

STATUS_PURCHASED = "purchased"
STATUS_PRINTED = "printed"
STATUS_QUEUED = "queued"
STATUS_CHECK_PRINTER = "check_printer"
STATUS_REFUNDED = "refunded"


@dataclass(frozen=True)
class LabelIdentity:
    """Who a label is for, as the journal knows it."""

    recipient_key: str
    recipient_label: str


def identity_for(address: AddressBase) -> LabelIdentity:
    """Build the journal identity of a recipient address.

    shippy (CLI) builds the same key from the same fields, so both apps see
    each other's labels.
    """
    street = " ".join(part for part in (address.street1, address.street2) if part)
    key = ibp_printing.recipient_key(
        address.name, street, address.city, address.state, address.zipcode
    )
    label = f"{address.name}, {address.street1}, {address.city}, {address.state}"
    return LabelIdentity(recipient_key=key, recipient_label=label)


def tracking_ref(shipment: Any) -> str:
    """The journal's key for a shipment: tracking code, else shipment id."""
    return shipment.tracking_code or shipment.id


def pending_labels() -> list[Any]:
    """Labels still waiting to print (call off the UI thread)."""
    return list(ibp_printing.pending_labels())


def record_purchase(identity: Optional[LabelIdentity], shipment: Any) -> Any:
    """Journal a just-bought label; returns the record (None if not journaled)."""
    if identity is None:
        return None
    try:
        return ibp_printing.record_purchase(
            recipient_key=identity.recipient_key,
            recipient_label=identity.recipient_label,
            tracking_code=tracking_ref(shipment),
            shipment_id=shipment.id,
            app=APP_NAME,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Could not journal purchase of %s", shipment.id)
        return None


def update_status(shipment: Any, status: str, *, file: Optional[Path] = None) -> None:
    """Journal a label's print outcome; never raises."""
    try:
        ibp_printing.update_status(
            tracking_ref(shipment), status, file=str(file) if file else None
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Could not journal status %s for %s", status, shipment.id)


def retry_meta(
    identity: Optional[LabelIdentity], shipment: Any, record: Any = None
) -> dict[str, Any]:
    """Metadata saved next to a queued label for the label watcher."""
    created = getattr(record, "created", None)
    meta: dict[str, Any] = {
        "tracking_code": tracking_ref(shipment),
        "shipment_id": shipment.id,
        "app": APP_NAME,
        # When postage was bought (epoch seconds, like the journal).
        "created": created if isinstance(created, (int, float)) else time.time(),
    }
    if identity is not None:
        meta["recipient_label"] = identity.recipient_label
        meta["recipient_key"] = identity.recipient_key
    return meta


def as_datetime(value: Any) -> Optional[datetime]:
    """Read a journal timestamp (epoch seconds) as local time."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).astimezone()
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return moment.astimezone() if moment.tzinfo else moment


def format_time(value: Any) -> str:
    """HH:MM of a journal timestamp (today), else a short date and time."""
    moment = as_datetime(value)
    if moment is None:
        return str(value or "?")
    if moment.date() == datetime.now(moment.tzinfo).date():
        return moment.strftime("%H:%M")
    return moment.strftime("%b %d %H:%M")
