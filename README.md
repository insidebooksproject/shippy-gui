# shippy-gui

`shippy-gui` is the PySide6 app the Inside Books Project (IBP) shipping
stations use to print shipping labels for books sent to people incarcerated in
Texas when the address is typed in ("Ship Manual"). Packages for a scanned
request or a unit go through the
[shippy CLI](https://github.com/insidebooksproject/shippy). It looks addresses up with Google Maps autocomplete, takes the return address
from the IBP server, buys the cheapest USPS postage through EasyPost, and
prints the label, with the IBP logo, through the shared
[ibp-printing](https://github.com/insidebooksproject/printing) library.

## About Inside Books Project

Inside Books Project is an Austin-based community service volunteer organization that sends free reading materials to people incarcerated in Texas, and also publishes resource guides and short-form instructional pamphlets. Inside Books is the only books-to-prisoners program in Texas, where more than 120,000 people are behind bars. Inside Books Project works to promote reading, literacy, and education among incarcerated individuals and to educate the general public on issues of incarceration.

## Features

- **Settings Dialog**: GUI for configuring the IBP server URL and API keys
- **Error Handling**: Labels that cannot reach a printer are saved to a print queue folder for the IBP label watcher (postage kept); automatic refund if the label itself cannot be downloaded
- **Async Operations**: Non-blocking UI using QThread for network operations
- **Configurable Font Size**: Adjust UI font size for accessibility

## Running shippy-gui

The stations run the `deploy` branch straight from GitHub with
[uv](https://github.com/astral-sh/uv)'s `uvx` (see [Releasing](#releasing)):

```bash
uvx --from git+https://github.com/insidebooksproject/shippy-gui.git@deploy shippy-gui
```

The shipping laptops' SHIP MANUAL shortcut runs
`uvx --from "shippy-gui[windows] @ git+https://github.com/insidebooksproject/shippy-gui.git@deploy" shippy-gui`;
the `windows` extra is empty and kept only so that command keeps working.
shippy-gui reads `config.ini` from the folder it is started in (see
[Configuration](#configuration)), so start it from the folder that holds it.

### Creating a Desktop Shortcut (Windows)

To create a Windows desktop shortcut that launches shippy-gui, you can use PowerShell:

```powershell
powershell.exe -NoExit -Command "& { & 'uvx' --from 'git+https://github.com/insidebooksproject/shippy-gui.git@deploy' 'shippy-gui' }"
```

To create the shortcut:

1. Right-click on your desktop
2. Select **New → Shortcut**
3. Paste the PowerShell command above as the location
4. Name the shortcut "Shippy GUI" (or your preferred name)
5. Click **Finish**
6. In the shortcut's **Properties**, set **Start in** to the folder with `config.ini`

#### Using a `.cmd` Launcher (Recommended)

For more reliable startup and an explicit config path, create a small `.cmd` file and point a shortcut at it.

Example `shippy-gui.cmd`:

```bat
@echo off
setlocal

REM Set working directory (where your config lives)
cd /d "C:\InsideBooks\ShippyGUI"

REM Run the app
uvx --from git+https://github.com/insidebooksproject/shippy-gui.git@deploy shippy-gui
```

To create the shortcut:

1. Save the `.cmd` file in a stable location
2. Right-click on your desktop and select **New → Shortcut**
3. Browse to the `.cmd` file
4. Name the shortcut and click **Finish**

## Configuration

The application requires a configuration file for the IBP server, the EasyPost API and the Google Maps API. The return address on every label comes from the IBP server's shipping settings (`GET /shipping-settings`), the same one `shippy` uses, and is read each time a label is bought; if the server can't be reached, no postage is bought.

### Initial Setup

shippy-gui reads `config.ini` from the current working directory. If it is missing, the app creates one from the packaged `config.example.ini`, shows a configuration error and opens Settings so you can fill in the required values; if it is incomplete or invalid, it shows the error and opens Settings too. If you cancel Settings, or the values are still invalid, the app exits. Settings are always saved to `config.ini`.

### Manual Configuration

1.  Copy `config.example.ini` to `config.ini` in your working directory.
    - Note: `config.example.ini` is in the repo root and also bundled inside the installed package for automatic bootstrap.
2.  Populate it with the IBP server URL and your API keys:

    ```ini
    [ui]
    font_size = 11
    log_file = shippy.log
    default_weight = 3

    [easypost]
    apikey = your_easypost_api_key_here

    [ibp]
    url = http://192.168.1.156/api

    [googlemaps]
    apikey = your_google_maps_api_key_here
    ```

    - `ui.font_size`: UI font size in points (8-24)
    - `ui.log_file`: Log file path (relative to config directory or absolute)
    - `ui.default_weight`: Default package weight in pounds
    - `easypost.apikey`: Your EasyPost API key
    - `googlemaps.apikey`: Your Google Maps API key (for address autocomplete)
    - `ibp.url`: The IBP server's API base URL (source of the return address)
    - `ibp.apikey` (optional, also in Settings): stored but not sent; the IBP server needs no key
    - `[parcel]` (optional): `length`, `width` and `height` in inches of the
      box declared unless the small-box checkbox is ticked (default 20 x 14 x 10).
      The small box is always declared as 12 x 12 x 12.

### Settings Dialog

You can also configure these settings from within the application:

1. Launch shippy-gui
2. Go to **File → Settings** (or press `Ctrl+,`)
3. Fill in the required fields
4. Click **Save**

The settings dialog validates your configuration and saves it to `config.ini`.

## Application Workflow

1. **Configure settings** (File → Settings) on first run
2. **Enter recipient address**:
   - Type an address in the search field and select from Google Maps autocomplete suggestions
   - Address fields auto-populate when you select a result
   - All fields are editable for manual adjustment
3. **Enter package weight** in pounds (1-70 range)
   - At 4 pounds and up, tick the box-size checkbox only if the box is 1,728
     cubic inches or less (each side rounded up to a whole inch) with no side
     over 22 inches; its tooltip has examples. Leave it unticked if unsure.
     Changing the address clears it.
4. **Select printer** from the dropdown (it updates by itself a few seconds
   after a printer is plugged in; **Refresh** scans right away)
5. **Click "Create Label"**:
   - If no label printer is found, a "No label printer detected" window waits
     for one and closes by itself when it appears. **Continue anyway** buys
     the label and saves it to `Downloads\to-print\` for the label watcher;
     **Cancel** buys nothing.
   - Application buys the cheapest USPS rate via EasyPost (Library Mail, or
     Ground Advantage when the small box makes it cheaper) and shows the rates
     it compared, tagging the shipment's `reference` as `ibp1:manual` so the IBP server can tell typed-address labels from request and unit labels (the `shippy` CLI tags those `ibp1:req:<code>` and `ibp1:unit:<jurisdiction>:<unit name>`)
   - Downloads label from EasyPost and overlays IBP logo from `assets/logo.jpg` when available
   - Prints to selected printer
   - Shows tracking number on success
   - If no printer can take the label, saves it to `Downloads\to-print\` to print later (postage is **not** refunded; see [Label did not print](#label-did-not-print))
   - Automatically refunds if the label cannot be downloaded or prepared

## Platform Support

Printer discovery and direct printing are provided by `ibp-printing`. Only
USB label printers are listed:

- **Direct USB**: a supported printer (the PM2411BT the shipping laptops use)
  is printed to directly over USB, with no print queue or naming rule, and is
  listed first, e.g. `PM2411BT (USB direct, serial ...)`.
- **Print queues** (Windows only, through win32print): the queue name must
  end with the printer's USB ID (e.g. `Zebra 20d1:7008`, `Zebra_20d1:7008` or
  `Zebra-20d1:7008`) and that USB device must be plugged in. Printers whose
  USB device or queue reports a problem are still listed, just lower down.
  Linux has no queues: only the direct USB printers print (`ibp-printing`
  dropped CUPS on 2026-11-26).

Shift + Click on "Create Label" uses the Qt system print dialog instead.
Canceling that dialog refunds the postage. If printing cannot even start, the
label is saved to `Downloads\to-print\` like any other label no printer took;
if it fails after printing started, you get the "Check The Printer" warning and
nothing is refunded right away.

### Printer logs

Every discovery and print attempt is logged in detail by `ibp-printing` to
`printer-shippy-gui.log` (human readable) and `printer-shippy-gui.jsonl` (one JSON object per line)
in `%LOCALAPPDATA%\ibp-printing\logs` on Windows
(`~/.local/state/ibp-printing/logs` on Linux). Printer messages at INFO and
above also appear in the shippy-gui log file.

## Keyboard Shortcuts

- `Ctrl+,` - Open Settings dialog
- `Ctrl+Q` - Quit application

## Troubleshooting

### "Configuration Error" on startup
- Ensure `config.ini` exists and is properly formatted
- Use File → Settings to validate and save your configuration

### "Failed to verify recipient address" warning
- This is non-blocking; the label is still bought
- Double-check the address manually before shipping
- "Failed to verify return address" means the return address in the IBP
  server's shipping settings (editable in the IBP web app) needs checking

### "Shipment Error"
The box says in plain words whether postage was bought; the technical details
(the EasyPost or IBP server error) go to the shippy-gui log file
(`ui.log_file`). The form is kept, so trying again is one click.

- "No postage was bought": creating the label failed before buying (the
  addresses, the quote or no usable rate), or EasyPost turned the purchase
  down. Try the shipment again.
- "The EasyPost account can't pay for postage right now": EasyPost refused the
  purchase for lack of funds; nothing was bought. Tell a coordinator, who can
  top up the EasyPost wallet.
- "The purchase may not have completed": the buy request got no answer, timed
  out or hit an EasyPost server error, so the charge may have gone through.
  Try the shipment again; if the first label was bought, it is never used and
  the weekly refund job refunds it.
- "The IBP server can't be reached": the return address could not be read, so
  nothing was bought. Check that the laptop is online and try again.
- "The IBP server didn't send a usable return address": the return address in
  the IBP server's shipping settings (IBP web app) needs fixing.

### Label did not print
If the label cannot be sent to any printer, the postage is kept and the label,
with the IBP logo, is saved to the print queue folder `Downloads\to-print\`.
A "Label Will Print Later" box says the label didn't print, names the
recipient and tracking number, and says it was saved and will print
automatically when the printer is working.

- If the IBP label watcher (from ibp-printing) is running, the label prints
  automatically as soon as a label printer is working - plug in or fix the
  printer and wait.
- Check that your printer is online and selected correctly.

The app only refunds right away when the label could not be downloaded or
prepared after buying postage, or when it could not even be saved to the queue.
Any label that is never used (never scanned by USPS) is refunded automatically
by the weekly refund job on the IBP server, so an occasional extra label costs
nothing.

### Label journal
Every label bought by shippy-gui or the shippy CLI is recorded in the shared
ibp-printing label journal (`labels.jsonl` in `%LOCALAPPDATA%\ibp-printing` on
Windows, `~/.local/state/ibp-printing` on Linux), together with what happened
to it: printed, queued in `to-print\`, waiting at the printer
(`check_printer`), or refunded. The label watcher and the "Waiting to print"
indicator read it. The app does not ask before buying another label for the
same address: several boxes to one person is normal.

### "Waiting to print: N"
The status bar shows **Waiting to print: N** while labels are queued in
`to-print\` or waiting at the printer (it is hidden when there are none, and
refreshes every 10 seconds and after each shipment). Click it to see who each
label is for, its tracking number, its status and when it was queued.

### "Check The Printer" warning
The label reached the print queue, but the queue then reported a problem (or
it could not be confirmed that the job got there, or printing failed with an
unexpected error after the label may have been sent). The label is **not**
queued again, because it may still print. The warning says: "Check the
printer. If no label came out, create it again; the unused one is refunded
automatically."

### Printer missing from the list
- Click **Refresh** after plugging in or turning on the printer
- Run `diagnose-printers` to see every printer and print queue and why it is or is not listed:
  `uvx --from git+https://github.com/insidebooksproject/shippy-gui.git@deploy diagnose-printers`
  on a station, or `uv run diagnose-printers` in a checkout
- Send the `printer-shippy-gui.log`/`printer-shippy-gui.jsonl` files (see [Printer logs](#printer-logs)) when reporting a problem

### Google Maps autocomplete not working
- Verify your Google Maps API key in Settings
- Ensure Places API is enabled in your Google Cloud Console
- Check that you have sufficient API quota

## Development

Install Python 3.12+ and [uv](https://github.com/astral-sh/uv), then:

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/insidebooksproject/shippy-gui.git
    cd shippy-gui
    ```

2.  **Create and activate a virtual environment:**

    ```bash
    uv venv
    source .venv/bin/activate
    ```

    On Windows, use `.venv\Scripts\activate`.

3.  **Install dependencies** (defined in `pyproject.toml`):

    ```bash
    uv sync
    ```

    Nothing platform-specific is needed: on Windows `pywin32` and `WMI` come
    in automatically, and on Linux printing goes directly over USB (install
    `ibp-printing`'s udev rule once; see its README). The `linux` and
    `windows` extras are empty, kept so existing `uv sync --extra ...`
    commands still work.

4.  **Run it** from the folder with `config.ini`:

    ```bash
    python -m shippy_gui
    ```

    or `shippy-gui`.

To enable Git hooks for linting and formatting checks:

```bash
uv run pre-commit install
```

Checks, tests and the code conventions are in [CLAUDE.md](CLAUDE.md).

Printing comes from the shared
[`ibp-printing`](https://github.com/insidebooksproject/printing) library, pinned
to a release tag in `pyproject.toml` (`[tool.uv.sources]`) and installed
automatically. To develop both together, temporarily point it at a checkout in
`../printing` with `{ path = "../printing", editable = true }`. Tag and push a
new ibp-printing release before pinning it here, or the stations fail to
install shippy-gui.

shippy-gui does not depend on the [shippy CLI](https://github.com/insidebooksproject/shippy):
`core/services.py` (EasyPost), `core/addresses.py` (Google Maps) and
`core/models.py` (config) are its own versions of the same logic, so a fix in
one app does not reach the other. What the two share is ibp-printing and the
IBP server.

### Releasing

`main` and `deploy` stay at the same tip. Merge feature branches straight
into `main` (no pull requests), test, then release by fast-forwarding
`deploy` to it:

```bash
git push origin main:deploy
```

The shipping laptops run `@deploy` with `uvx` at every launch, and the kiosk
image installs shippy-gui from `deploy` as a uv tool, so both pick up the
release at the next launch. Never commit to `deploy` directly. To roll back,
push the previous commit to `deploy` with `--force-with-lease`.

## License

This project is developed for the Inside Books Project. For licensing information, please contact IBP directly.
