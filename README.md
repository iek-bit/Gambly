# Number Guessing Gambling Game

## Overview
A Python number-guessing gambling game with persistent account data in `accounts.json`.

The app uses a Streamlit web app UI.

## Features
- Create accounts with initial deposit
- Password-protected sign-in
  - First sign-in for legacy/no-password accounts prompts password setup
- Single active sign-in session per account (guest mode is unaffected)
- Signed-in users can change their own password (current password required)
  - In Streamlit UI, this is in the profile/avatar menu
- Look up account balances
- Add/withdraw money (signed-in account only, with re-authentication)
- Two game modes
  - Player guesses the number
  - Computer guesses the player's number
- Blackjack mode (player vs computer dealer, configurable pre-round bet)
  - Supports signed-in play and guest mode
  - Visual card table with deck + dealt cards
- All-time stat filters for:
  - All games combined
  - Number guessing (you guess)
  - Number guessing (computer guesses)
  - Blackjack
- Break-even odds calculator
- Persistent house odds multiplier
- Admin account support (`isaac` in Streamlit UI)

## Requirements
- Python 3.9+
- Streamlit for web UI

## Run
Web UI (primary):
```bash
streamlit run streamlit_app.py
```

App entrypoint:
```bash
python main.py
```

## Deploy (Streamlit Community Cloud)
1. Push this project to GitHub.
2. Go to https://share.streamlit.io and sign in.
3. Click `New app`.
4. Select your repo, branch, and set main file path to `streamlit_app.py`.
5. Click `Deploy`.

### Important persistence note
- This app currently stores runtime data in `accounts.json`.
- On Streamlit Community Cloud, runtime file writes are not reliable for long-term persistence.
- For production-like persistence, move storage to a hosted database (for example Supabase Postgres or Turso).

## Account File Format
Data is stored in `accounts.json` as structured JSON:

```json
{
  "odds": 1.5,
  "active_sessions": {
    "example_user": {
      "session_id": "example_session_id",
      "last_seen_epoch": 1739385600.0
    }
  },
  "accounts": {
    "example_user": {
      "balance": 100.0,
      "password": "example_password"
    }
  }
}
```

## Reserved Names / Codes
- `__house_odds__`: internal storage key for odds multiplier

## Authentication Behavior
- To sign in, user must provide account password.
- If password is not yet set for that account, user is prompted to create one at sign-in.

## Money Action Behavior
Menu option `add/withdraw money`:
- Requires signed-in account
- If no account is signed in, app redirects to sign-in and returns to the same task
- Requires password re-authentication before applying change
- Uses signed amount:
  - positive = add
  - negative = withdraw

## Game Math
Break-even payout:
```text
(num_range * price_per_round) / (2 ** (guesses - 1))
```

House edge application:
- Player-guesses mode payout: `floor(break_even / odds)`
- Computer-guesses mode loss payout: `ceil(break_even * odds)`

## Admin Controls
- In Streamlit, `isaac` is the super-admin and can:
  - updating house odds
  - changing any account balance
  - changing any account password (with confirmation)
  - viewing any account password
  - deleting any account
  - granting/revoking admin access for other accounts in Account Tools
- Admins created by `isaac` get all admin tools except granting/revoking admin access.

## Project Structure
- `main.py`: program entrypoint and top-level menu flow orchestration
- `streamlit_app.py`: primary Streamlit frontend
- `storage.py`: file persistence for accounts, passwords, and odds
- `auth.py`: password setup/verification and sign-in routing helpers
- `account_ops.py`: account creation logic
- `gameplay.py`: game logic and round loops
- `accounts.json`: persisted runtime data
