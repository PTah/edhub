# Uploading journal data (EDSM / EDDN / INARA)

EDHUD can push **live** Elite Dangerous journal events to community services.
This is optional and controlled in **Settings**.

| Service | Setting | Credentials | What is sent |
|---|---|---|---|
| **EDSM** | Commander + API key | Personal EDSM key | Jumps with coordinates, scans, docking, FSS/SAA, etc. (`api-journal-v1`) |
| **EDDN** | “Send to EDDN” checkbox | None | Live `Scan`, `FSDJump`, `Location`, `Docked`, `SAASignalsFound`, `FSSBodySignals`, `CodexEntry`, `FSSDiscoveryScan` → `https://eddn.edcd.io:4430/upload/` |
| **INARA** | Commander + API key | Personal INARA key | Travel only: `FSDJump`, `Location`, `CarrierJump`, `Touchdown` → `https://inara.cz/inapi/v1/` |

**Spansh** has no public write API. It (and much of INARA’s body data) consumes the **EDDN** bus.

## Requirements

* Network allowed in Settings (`allow_network`).
* **Live** game only (Odyssey / Horizons 4.x). Legacy 3.8 is not uploaded.
* Do not backfill old journals to EDDN/INARA (services ask for live data). EDSM may backfill position events (`FSDJump` / `Location` / `CarrierJump` with `StarPos`) once when enabled.

## EDDN

* No API key. Header uses `uploaderID` = commander name, `softwareName` = `EDHUD`.
* Success is recorded in `%LOCALAPPDATA%\EliteDangerousHUD\eddn-sent.json`.
* Receiving the live feed (`eddn_enabled`) is separate from uploading (`eddn_upload`).

## EDSM

* Needs commander name + API key from EDSM.
* Progress: `edsm-sent.json`.

## INARA

* Needs commander name + personal API key from [INARA settings](https://inara.cz/).
* Request header uses `appName`: **`EDHUD`**. That name must be **whitelisted** by INARA (see [developer guide](https://inara.cz/elite/inara-api-devguide/)). Until then the API returns `This application has no access allowed`.
* Body scans are **not** sent via INARA API; enable EDDN upload so INARA can pick them up from the bus.
* Progress: `inara-sent.json`.

## Privacy

Only events you generate in your own journal are uploaded. API keys stay in local `config.json` and are never committed to the repository.
