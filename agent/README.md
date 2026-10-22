# Comstore relay agent

Carries eTIMS requests from a cloud ERPNext to the Comstore device on the shop's
network. Run it on the same PC as ComstoreFC4Api (or any PC that can reach it).

It only makes **outgoing** connections: it asks ERPNext over HTTPS for waiting
requests, sends each to the Comstore API, and posts the answer back. No ports are
opened at the shop, and the device's API key stays on this PC.

## Requirements

- Python 3.8 or later (standard library only; nothing to `pip install`).
- ComstoreFC4Api running, with a successful *Test Connection* to the device.

## Set up

1. In ERPNext, create a user with **only** the *Comstore Relay* role. Open the
   user, *Settings > API Access > Generate Keys*, and copy the key and secret.
2. On the Comstore Device in ERPNext, set *Connection* to **Relay** and *Relay
   User* to that user.
3. On the shop PC, put `comstore_relay.py` in a folder, copy
   `comstore_relay.example.ini` to `comstore_relay.ini` beside it, and fill in:
   the site URL, the relay user's key and secret, the device serial number, and
   the Comstore API key.
4. Run it once by hand and watch for `Relaying for device ...`:

   ```bat
   python comstore_relay.py
   ```

   On the Comstore Device in ERPNext, *Relay Last Seen* updates within a minute.

## Keep it running

Use Windows Task Scheduler: a task that runs at start-up (*Run whether user is
logged on or not*), action `python.exe` with argument the full path to
`comstore_relay.py`, and *If the task fails, restart every 1 minute*. NSSM works
too if you prefer a Windows service.

The agent logs to `comstore_relay.log` beside its `.ini`.

## If it stops

Requests it claimed but never answered return to ERPNext's queue after ten
minutes and are sent again. Re-sending a signature is safe: for a live invoice
the device recognises one it has already signed and returns the original
signature.

## Tests

```bash
python -m unittest discover -s agent -p "test_*.py"
```
