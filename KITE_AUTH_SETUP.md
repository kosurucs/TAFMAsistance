# Zerodha Kite Authentication Setup Guide

## Redirect URL Modes (Both Supported)

TAFMAsistance supports two valid Kite redirect setups.

### Mode A: UI Callback (Recommended)

Set Redirect URL in Kite app settings to:

```text
http://localhost:5173/login
```

This enables automatic callback detection in the login page.

### Mode B: Local HTTPS Callback (Supported)

Set Redirect URL in Kite app settings to:

```text
https://localhost:7049
```

This mode is useful if your app is already configured for localhost HTTPS callback. If redirect does not land on the UI route, use manual exchange in the login page.

## Steps to Configure

### 1. Update Kite App Settings

1. Open https://developers.kite.trade/apps
2. Select your app
3. Set Redirect URL to one of:
   - `http://localhost:5173/login` (recommended)
   - `https://localhost:7049` (supported fallback)
4. Save

### 2. Configure Credentials

Provide in `.env` (or via UI credentials setup):

```env
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
```

Access token fields are auto-managed:

```env
KITE_ACCESS_TOKEN=auto_updated_by_app
KITE_TOKEN_TIMESTAMP=auto_updated_by_app
```

## Authentication Flow

1. Open `http://localhost:5173/login`
2. If credentials are missing, save API key and API secret
3. Click `Login with Zerodha Kite`
4. Login on Zerodha
5. Exchange token:
   - Mode A: callback is auto-detected by UI
   - Mode B: paste callback URL or request token in manual fallback box
6. Backend exchanges `request_token` via `POST /api/auth/exchange`
7. App stores token and validates connection

## Token Expiration

- Kite access tokens expire every 24 hours
- App checks token age and validity at startup
- Re-login is required after expiry

## Manual Token Exchange (Advanced)

You can exchange using either raw token or full callback URL.

### Swagger

1. Open `http://localhost:8000/docs`
2. Call `POST /api/auth/exchange`
3. Send one of:
   - `{"request_token": "YOUR_TOKEN"}`
   - `{"callback_url": "https://localhost:7049/?status=success&request_token=YOUR_TOKEN&action=login"}`

### cURL examples

```bash
curl -X POST http://localhost:8000/api/auth/exchange \
  -H "Content-Type: application/json" \
  -d "{\"request_token\":\"YOUR_TOKEN\"}"
```

```bash
curl -X POST http://localhost:8000/api/auth/exchange \
  -H "Content-Type: application/json" \
  -d "{\"callback_url\":\"https://localhost:7049/?status=success&request_token=YOUR_TOKEN&action=login\"}"
```

## Troubleshooting

### Callback does not return to UI

Cause: Redirect URL is `https://localhost:7049` or browser/cert behavior prevented UI route callback.

Fix:
1. Copy full callback URL or `request_token`
2. Open `http://localhost:5173/login`
3. Use manual fallback exchange field

### Authentication fails after callback

Cause: Invalid API secret or single-use token already consumed.

Fix:
1. Verify `KITE_API_SECRET`
2. Retry login to generate new `request_token`
3. Re-run exchange once

### Token expired

Cause: Normal 24-hour expiry.

Fix: Login again.

## Security Notes

- Never commit `.env`
- Rotate API secret immediately if exposed
- Treat API key and secret as sensitive credentials
- System is analysis-only; order placement endpoints are disabled
