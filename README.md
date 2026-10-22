# Comstore eTIMS for ERPNext

A Frappe app that signs ERPNext sales invoices and credit notes for KRA eTIMS
through a **Comstore Smart VSCU (FC4)** fiscal device, using the vendor's
`ComstoreFC4Api` service (v3.6.x).

It works on any ERPNext v16 site, including shops running UpeoRetail, because
everything they sell posts a Sales Invoice.

## What it does

- **Signs every submitted Sales Invoice** on the device, after the submit has
  committed. A device that is off never stops a sale: the invoice shows
  *eTIMS: Queued*, then *Signed* or *Failed* with the device's reason.
- **Credits returns.** A return invoice is sent as an eTIMS credit note against
  the original's CU invoice number, with a refund reason.
- **Stores the receipt fields** on the invoice: CU invoice number, SCU ID,
  internal data, receipt signature, verification link and transmit status. Print
  formats can draw the QR code with `{{ comstore_qr(doc.comstore_signature_link) }}`.
- **Registers items and buyers** on the device (it refuses to sell an item it
  does not know), from buttons on the Comstore Device.
- **Watches the device**: connection, invoices waiting to reach KRA, and a button
  to push them. Failed signings caused by an unreachable device are retried.

## How it reaches the device

The Comstore API runs on a Windows PC on the shop's network and listens on plain
HTTP (port 4000 by default). A cloud ERPNext cannot reach it. Each Comstore
Device therefore chooses a connection:

| Connection | Use when | How it works |
|---|---|---|
| **Relay** (default) | ERPNext is in the cloud | The relay agent on the shop's PC collects waiting requests over HTTPS, calls the API locally and posts the answers back. The shop opens no ports, and the device's API key never leaves the shop. |
| **Direct** | ERPNext can reach the shop's network (on-premise, VPN) | The server calls the API itself from a background job. |

Every call is a **Comstore Request** document either way, so there is one log of
what was sent and what came back.

## Install

```bash
bench get-app https://github.com/Upeosoft-Limited/comstore-etims
bench --site your.site install-app comstore_etims
```

## Set up

1. **Company:** set the company's **Tax ID** to its KRA PIN (e.g. `P000111222Z`).
2. **Comstore Device:** add one per fiscal device: serial number, company, the
   device's IP address, and the connection.
   - *Relay:* create a user with only the **Comstore Relay** role, generate its
     API key and secret, and set it as the device's Relay User.
   - *Direct:* the API URL (e.g. `http://192.168.1.50:4000`) and the API key
     shown by the ComstoreFC4Api app.
3. **Comstore Settings:** tick *Enabled*, choose the default device and the
   default tax types. Keep **Test Mode** on until a test invoice signs cleanly:
   in test mode the device signs without sending anything to KRA.
4. **Items:** set each item's **eTIMS Tax Type** (or rely on its Item Tax
   Template), then use **Device > Upload New Items**. An item must be on the
   device before it can be sold.
5. Submit a Sales Invoice and check its *eTIMS* section.

### Tax categories

| Type | Rate | |
|---|---|---|
| A-Exempt | 0% | exempt |
| B-16.00% | 16% | standard |
| C-0% | 0% | zero rated |
| D-Non-VAT | – | not subject to VAT |
| E-8% | 8% | tourism |

An item's category comes from its *eTIMS Tax Type*, else its Item Tax Template's
rate, else the default in Comstore Settings. Signing refuses an invoice whose
charged tax does not match the item's category, rather than letting the device
reject it later.

## Relay agent

`agent/comstore_relay.py` is a single Python 3 file with no dependencies. On the
PC running ComstoreFC4Api:

```bat
copy comstore_relay.example.ini comstore_relay.ini
rem edit comstore_relay.ini: site URL, relay user's API key/secret, device serial, Comstore API key
python comstore_relay.py
```

Run it at start-up with Task Scheduler (or NSSM) so it survives restarts. See
[agent/README.md](agent/README.md).

## Tests

```bash
bench --site your.site set-config allow_tests true
bench --site your.site run-tests --app comstore_etims
python -m unittest discover -s agent -p "test_*.py"
```

## Licence

MIT. Comstore, ComstoreFC4Api and Smart VSCU are products of Dejavu Technology
Solutions Limited; this project is not affiliated with them. Use the vendor's
documentation for the device and API themselves.
