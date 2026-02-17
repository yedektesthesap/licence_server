# CCM License Server MVP

Minimal FastAPI + SQLite licensing server for CCM daemon.

## Quickstart

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -e .
pip install -e .[dev]
```

Run server locally:

```bash
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=change-this-password
python -m app.main
```

Environment variables:

- `DB_PATH` (default: `./data/licenses.db`)
- `TOKEN_TTL_SECONDS` (default: `86400`)
- `HOST` (default: `0.0.0.0`)
- `PORT` (default: `8000`)
- `ADMIN_USERNAME` + `ADMIN_PASSWORD` (both required together for `/admin`)

## Admin CLI

Create license (auto key):

```bash
python -m app.admin create-license --days 30 --note "trial"
```

Create license (custom key):

```bash
python -m app.admin create-license --days 30 --key ABCD-EFGH-JKLM
```

Disable license:

```bash
python -m app.admin disable-license --key ABCD-EFGH-JKLM
```

Enable (reactivate) license:

```bash
python -m app.admin enable-license --key ABCD-EFGH-JKLM
```

Generate license key:

```bash
python -m app.admin generate-key
```

List licenses:

```bash
python -m app.admin list-licenses
```

Show one license:

```bash
python -m app.admin show-license --key ABCD-EFGH-JKLM
```

## API

### `POST /v1/token`

Request:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/token \
  -H "Content-Type: application/json" \
  -d '{
    "license_key": "ABCD-EFGH-JKLM",
    "app_id": "ccm",
    "app_version": "1.0.0"
  }'
```

Allowed response example:

```json
{
  "allowed": true,
  "lease": {
    "lease_id": "9f395f9d-cbca-4425-9987-5ce18b3f2948",
    "issued_at": "2026-02-13T15:00:00Z",
    "expires_at": "2026-02-14T15:00:00Z"
  },
  "license": {
    "license_key": "ABCD-EFGH-JKLM",
    "issued_at": "2026-02-01T00:00:00Z",
    "duration_days": 30,
    "license_expires_at": "2026-03-03T00:00:00Z",
    "remaining_time": {
      "years": 0,
      "months": 0,
      "days": 17,
      "hours": 0,
      "minutes": 0,
      "seconds": 0
    }
  },
  "token_ttl_seconds": 86400,
  "server_time": "2026-02-13T15:00:00Z"
}
```

Denied response example:

```json
{
  "allowed": false,
  "reason": "expired",
  "server_time": "2026-02-13T15:00:00Z"
}
```

## Admin Web Panel

Admin UI path:

- `GET /admin` (HTTP Basic Auth)

Capabilities:

- Create license
- Generate license key
- Disable license
- Enable (reactivate) disabled license
- List all licenses

PowerShell example:

```powershell
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="change-this-password"
python -m app.main
```

Open:

- `http://127.0.0.1:8000/admin`

## Run As A Linux Service (systemd)

Files:

- Unit: `deploy/ccm-license-server.service`
- Env example: `deploy/ccm-license-server.env.example`

Install example:

```bash
sudo cp deploy/ccm-license-server.service /etc/systemd/system/ccm-license-server.service
sudo cp deploy/ccm-license-server.env.example /etc/default/ccm-license-server
sudo systemctl daemon-reload
sudo systemctl enable --now ccm-license-server
sudo systemctl status ccm-license-server
```

## Testing

```bash
pytest
```

## Licensing MVP

This MVP intentionally has limited scope:

- Relies on HTTPS transport trust only.
- No signed tokens.
- No device binding.
- No payment integration.

## Next version

- Signed tokens (JWS/Ed25519)
- Device activation
- Revocation
- Rate limiting
- Audit logs
- Stripe webhooks
- Admin UI
- Metrics
