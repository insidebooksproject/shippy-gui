"""Worker thread for creating and printing shipping labels."""

import logging
from typing import Optional

from PySide6.QtCore import QThread, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.ibp_server import (
    IbpServerError,
    IbpServerUnreachable,
    fetch_return_address,
)
from shippy_gui.core.models import RecipientAddress
from shippy_gui.core.services import ShipmentService
from shippy_gui.core.shipment_workflow import (
    CHECK_PRINTER_ADVICE,
    PURCHASE_UNCERTAIN_MESSAGE,
    ShipmentWorkflowInput,
    ShipmentWorkflow,
    ShipmentWorkflowStatus,
)

logger = logging.getLogger(__name__)

# What the volunteer is told when the return address can't be read; the
# technical details go to the log.
SERVER_UNREACHABLE_MESSAGE = (
    "The IBP server can't be reached, so no postage was bought. Check that "
    "this laptop is online, then try this shipment again."
)
SERVER_BAD_ADDRESS_MESSAGE = (
    "The IBP server didn't send a usable return address, so no postage was "
    "bought. Try this shipment again; if it keeps happening, the return "
    "address in the IBP server's shipping settings needs fixing."
)


class ShipmentWorker(
    QThread
):  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Worker thread for async shipment creation and printing."""

    # Signals
    progress = Signal(str)  # Progress message
    success = Signal(str)  # Success message
    # Spooled (so not refunded) but the print queue reported a problem.
    success_with_warning = Signal(str)
    # No printer took the label; it was saved to the print queue folder and
    # postage was kept (not refunded). Carries the ShipmentWorkflowResult.
    label_saved = Signal(object)
    error = Signal(str)  # Error message
    warning = Signal(str)  # Warning message (non-blocking)
    # (image, printer_name, shipment_object, ShipmentWorkflowResult)
    label_ready = Signal(object, str, object, object)

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        shipment_service: ShipmentService,
        ibp_url: str,
        to_address: RecipientAddress,
        weight_lbs: int,
        printer_name: str,
        logo_path: Optional[str] = None,
        use_dialog: bool = False,
        small_box: bool = False,
    ):
        """Initialize the shipment worker.

        Args:
            shipment_service: Shipment logic service
            ibp_url: IBP server base URL, read for the return address
            to_address: Recipient address model
            weight_lbs: Package weight in pounds
            printer_name: Name of printer to use
            logo_path: Optional path to logo image to overlay
            use_dialog: Whether to use system print dialog (default: False)
            small_box: Box is at most one cubic foot (declared as 12x12x12)
        """
        super().__init__()
        self.workflow = ShipmentWorkflow(shipment_service)
        self.ibp_url = ibp_url
        self.to_address = to_address
        self.weight_lbs = weight_lbs
        self.printer_name = printer_name
        self.logo_path = logo_path
        self.use_dialog = use_dialog
        self.small_box = small_box
        self.shipment = None
        # Quoted rates vs the one bought, for the final status line.
        self.rate_summary = None

    def run(self):
        """Execute the shipment workflow, reporting any unexpected crash."""
        try:
            self._run()
        except Exception:  # pylint: disable=broad-exception-caught
            # Never die silently: by now postage may have been bought and the
            # label may have been sent, so tell the volunteer rather than refund.
            # Unused labels are refunded automatically, so trying again is safe.
            logger.exception("Shipment worker crashed")
            shipment_ref = getattr(self.shipment, "tracking_code", None) or getattr(
                self.shipment, "id", None
            )
            if shipment_ref is None:
                self.error.emit(PURCHASE_UNCERTAIN_MESSAGE)
            else:
                self.error.emit(
                    "Something went wrong after postage was bought (tracking "
                    f"{shipment_ref}). {CHECK_PRINTER_ADVICE}"
                )

    def _run(self):
        self.progress.emit("Getting return address from the IBP server...")
        try:
            from_address = fetch_return_address(self.ibp_url)
        except IbpServerError as error:
            logger.error("Return address lookup failed", exc_info=True)
            self.error.emit(
                SERVER_UNREACHABLE_MESSAGE
                if isinstance(error, IbpServerUnreachable)
                else SERVER_BAD_ADDRESS_MESSAGE
            )
            return

        prepared_result = self.workflow.prepare_label(
            ShipmentWorkflowInput(
                from_address=from_address,
                to_address=self.to_address,
                weight_lbs=self.weight_lbs,
                logo_path=self.logo_path,
                small_box=self.small_box,
            ),
            on_progress=self.progress.emit,
            on_warning=self.warning.emit,
        )

        if prepared_result.status is ShipmentWorkflowStatus.ERROR:
            self.error.emit(prepared_result.message)
            return

        self.shipment = prepared_result.shipment
        self.rate_summary = prepared_result.rate_summary
        if self.use_dialog:
            self.label_ready.emit(
                prepared_result.image,
                self.printer_name,
                self.shipment,
                prepared_result,
            )
            return

        print_result = self.workflow.print_prepared_label(
            prepared_result=prepared_result,
            printer_name=self.printer_name,
            on_progress=self.progress.emit,
        )
        if print_result.status is ShipmentWorkflowStatus.SUCCESS:
            if print_result.saved_label_path is not None:
                self.label_saved.emit(print_result)
            elif print_result.print_warning:
                self.success_with_warning.emit(print_result.message)
            else:
                self.success.emit(print_result.message)
            return

        self.error.emit(print_result.message)
