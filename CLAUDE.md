# shippy-gui — Claude Code Instructions

## Project Overview

`shippy-gui` is a PySide6 desktop application for the Inside Books Project (IBP) that streamlines printing shipping labels for books sent to incarcerated individuals in Texas. It integrates with EasyPost for postage/label generation and Google Maps for address autocomplete.

**Package name:** `shippy_gui`
**Entry point:** `src/shippy_gui/__main__.py` → `main()`
**Python version:** 3.12 (see `.python-version`)
**Dependency/environment manager:** `uv` (lockfile: `uv.lock`)

## Project Structure

```
src/shippy_gui/
  __main__.py          # App entry point; config bootstrap and startup
  main_window.py       # Top-level QMainWindow
  shipping_tab.py      # Main shipping form tab
  settings_dialog.py   # Settings/config dialog
  shipping_coordinators.py # Create Label flow: printer gate, box answer, result dialogs
  core/
    config.py          # INI loading via configparser
    config_manager.py  # ConfigManager class (load/save/validate)
    models.py          # Pydantic models for config validation
    constants.py       # App-wide constants
    services.py        # EasyPost API wrapper (cheapest USPS rate, small-box parcel)
    rates.py           # Quoted-rates summary shown after buying
    ibp_server.py      # Return address from GET /shipping-settings
    addresses.py       # Google Maps geocoding/autocomplete
    logging.py         # Logging setup
    font.py            # Font size application
    misc.py
    shipment_workflow.py # Buy/print/save/refund orchestration
    label_journal.py   # Shared ibp-printing label journal (purchases, statuses)
  widgets/
    address_form.py    # Address entry widget
    shipment_controls.py
    autocomplete.py    # Google Maps autocomplete widget
    label_queue.py     # "Label Will Print Later" box, "Waiting to print" indicator
    printer_gate.py    # NoPrinterDialog shown before buying without a printer
  workers/
    shipment_worker.py # QThread worker for async shipment creation
  printing/
    printer_manager.py # Thin adapters over ibp_printing + Qt print dialog
    models.py          # PrinterInfo (UI model built from ibp_printing candidates)
  assets/
    logo.jpg           # IBP logo overlaid on labels
  config.example.ini   # Bundled template; also in repo root for dev
```

The `diagnose-printers` console script is `ibp_printing.diagnostics:main`
(the same tool as ibp-printing's `ibp-print-diag`).

## Environment Setup

```bash
uv venv
source .venv/bin/activate
uv sync --extra linux   # or --extra windows on Windows
uv run pre-commit install
```

`uv sync` also installs the `dev` group (black, mypy, pylint). `ibp-printing`
is pinned to a git tag of https://github.com/insidebooksproject/printing in
`[tool.uv.sources]`; to develop both together, temporarily point it at a
checkout in `../printing` (`{ path = "../printing", editable = true }`).

## Running the App

Run from the repository root so `config.ini` resolves:

```bash
python -m shippy_gui
# or
shippy-gui
```

## Configuration

- `config.ini` in the working directory (gitignored, never commit)
- `config.example.ini` is the template (committed to repo, with a copy in `src/shippy_gui/` bundled for bootstrap); real settings belong only in `config.ini`
- On first launch, the app auto-creates `config.ini` from the bundled example and opens the Settings dialog
- If you change setup, config fields, startup, platform behaviour or the volunteer-visible workflow, update `README.md` (and, for config fields, both copies of `config.example.ini`) in the same unit of work

## Code Quality

Pre-commit hooks run on every commit (CI runs the same on Linux and Windows):
- `pylint` — `uv run pylint src`
- `mypy` — `uv run mypy src`
- `black --check` — `uv run black --check src`
- `unittest` — the test command below

Format code before committing: `uv run black src`

Run tests (requires offscreen Qt platform for headless/hook contexts):
```bash
QT_QPA_PLATFORM=offscreen uv run python -m unittest discover -s tests
```

Run the checks that match what you touched; add an app launch smoke check
when changing UI or startup code. If you cannot run a meaningful check, say so.

## Git Workflow

- All work is done on **feature branches** branched from `main`.
- Commits must be **atomic and focused** — each commit should represent the smallest coherent unit of change; do not mix unrelated changes.
- Use **single-line commit messages** with an appropriate conventional tag:
  - `feat:` — new feature
  - `bugfix:` — bug fix
  - `refactor:` — code restructuring without behavior change
  - `chore:` — build, deps, tooling, config
  - `docs:` — documentation only
  - `test:` — tests only
- Do **not** include "Co-Authored-By" or any AI attribution in commit messages.
- Merge feature branches straight into `main` with `git merge --no-ff`; no
  pull requests and no review (one maintainer).
- `main` and `deploy` are kept identical, and every station runs `deploy`:
  release by fast-forwarding it (`git push origin main:deploy`) after the
  change is tested; never commit to `deploy` directly or let it diverge from
  `main`. Details and rollback: [README.md](README.md#releasing).

## Key Patterns

- Keep changes focused and within the existing module boundaries; preserve the PySide6 signal/slot patterns. Never hardcode secrets, API keys, printer names or machine-specific paths.
- Configuration is validated with Pydantic models (`core/models.py`); always use `ConfigManager` or `load_config()` — never read `config.ini` directly.
- Network operations (EasyPost, Google Maps) run in `QThread` workers to keep the UI non-blocking.
- Printing (discovery, platform backends, USB VID:PID matching, job tracking, printer logs) lives in the shared `ibp-printing` library (`ibp_printing`). `printing/printer_manager.py` is only a thin adapter; fix printer behaviour in ibp-printing, not here, and do not add platform checks to shippy-gui.
- `ibp_printing.configure_logging(app="shippy-gui")` is called at startup (`core/logging.py`), writing `printer-shippy-gui.log`/`printer-shippy-gui.jsonl` to `%LOCALAPPDATA%\ibp-printing\logs` (`~/.local/state/ibp-printing/logs` on Linux); INFO+ printer records also reach the app log.
- Tests fake printers with `ibp_printing.set_backend(FakeBackend())` (see `tests/test_printer_manager.py`); reset with `set_backend(None)`.
- Refund rules after postage is bought — preserve them when touching `shipment_worker.py` / `core/shipment_workflow.py` (covered by `tests/test_shipment_workflow.py`):
  - **No label image yet** (label download, decoding, or logo fails): refund.
  - **`ibp_printing.PrintError`** (the job definitely reached no printer): do NOT refund. Save the rendered label (with logo) with `ibp_printing.save_for_retry(image, name=tracking_code, meta=...)` into `<Downloads>/to-print/`, where the IBP label watcher prints it once a printer works. The volunteer is told via `ShipmentWorker.label_saved` (status line + calm "Label Will Print Later" information box from `widgets/label_queue.py`: the label didn't print, recipient, tracking, and that it will print automatically when the printer is working; the form is cleared like a success). Only if saving fails is the shipment refunded.
  - **Spooled but not `.ok`** (incl. `JobOutcome.UNCERTAIN` / `TRACKING_FAILED`): do NOT refund (the label may still print) and do NOT queue it; warn via `ShipmentWorker.success_with_warning` ("Check The Printer": it may not have printed; `CHECK_PRINTER_ADVICE` tells the volunteer to create it again if no label came out, since the unused one is refunded automatically).
  - **Any other exception from the print call** (not a `PrintError`): treated as uncertain, because the job may have reached the spooler — warn via `success_with_warning`, do NOT refund, do NOT save. Refund contexts cover only label preparation and the save-for-retry-failed fallback; building/showing messages after a spool or save must never refund.
  - **Shift+Click Qt dialog path** (`print_image_with_dialog` → `DialogPrintStatus`, handled in `shipping_coordinators.py`): `CANCELED` → refund; `NOT_SENT` (failed before `QPainter.begin()` succeeded) → `ShipmentWorkflow.save_unprinted_label` + "Label Will Print Later" box (refund only if saving fails); `UNCERTAIN` (failed after `begin()`) → "Check The Printer" warning, no refund.
- Error messages before printing name the stage, not the raw error (details go to the log with `exc_info`): before the buy request (addresses, quote, no rate) → `NOT_BOUGHT_MESSAGE` ("No postage was bought"); the buy request itself (`ShipmentService.buy_shipment` raises `PurchaseError`) → `PURCHASE_UNCERTAIN_MESSAGE` (may not have completed; try again, an unused label is refunded automatically), with no refund attempt; return address from the IBP server → `SERVER_UNREACHABLE_MESSAGE` (`IbpServerUnreachable`) or `SERVER_BAD_ADDRESS_MESSAGE` in `shipment_worker.py`.
- Volunteer prompts stay minimal: unused labels (never scanned by USPS) are refunded automatically every week by `ibp-label-refund.timer` on the IBP server, so an occasional duplicate or unprinted label is an accepted risk. Do not add a duplicate-label question, purchase-path reconciliation, or "do NOT create it again" / "delete it from to-print" / "refund in EasyPost" instructions to volunteer-facing texts.
- Printer check before buying: `ShipmentControls.start_printer_polling()` (started by `ShippingTab`) re-scans `get_available_printers()` on a background thread every `PRINTER_POLL_MS`, paused while the controls are disabled (a label in progress), and drives the printer status line. Before buying (not on Shift+Click), `ShipmentFlowCoordinator` calls `widgets/printer_gate.wait_for_printer`: with no printer it shows `NoPrinterDialog`, which closes itself once a scan finds one; "Continue anyway" buys with an empty printer name, and `print_prepared_label` then saves the label for the watcher (as a `PrintError`) without trying to print.
- Shared label journal (ibp-printing, also written by the shippy CLI and the label watcher), wrapped by `core/label_journal.py` (`app="shippy-gui"`):
  - There is no duplicate check before buying: shipping several boxes to one address is normal work. `identity_for` builds `recipient_key` from the recipient address (street1 + street2 joined by a space, same as shippy) for the purchase record and the label watcher's metadata.
  - **After buying**, `ShipmentWorkflow.prepare_label` calls `record_purchase`; the print outcome then sets `printed`, `check_printer` (spooled but not ok, uncertain/unexpected errors, dialog `UNCERTAIN`), `queued` (with the saved file) or `refunded` (only when the app's refund succeeded). Journal calls never raise and must never change the refund rules above.
  - `widgets/label_queue.py` `PendingLabelsIndicator` shows "Waiting to print: N" in the status bar (hidden at 0), reading `pending_labels()` on a background thread every 10 s and after each shipment.
  - Tests never touch the real journal: use `tests/journal_fakes.install_fake_journal(self)`, or `ibp_printing.labels.set_journal_path(tmp)` when calling the real `save_for_retry`.
