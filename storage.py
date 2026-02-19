"""Persistent storage helpers for accounts and odds."""

import json
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from money_utils import house_round_balance, house_round_credit, house_round_delta
from poker_bots import choose_bot_action
from poker_engine import apply_action as poker_apply_action
from poker_engine import create_hand as poker_create_hand
from poker_engine import from_cents
from poker_engine import legal_actions as poker_legal_actions

DEFAULT_ODDS = 1.5
ODDS_ACCOUNT_KEY = "__house_odds__"
GAME_STAT_KEYS = {"player_guess", "computer_guess", "blackjack", "poker"}
DEFAULT_ACCOUNT_SESSION_TTL_SECONDS = 6 * 60 * 60

SUPABASE_TABLE_DEFAULT = "app_state"
SUPABASE_STATE_ROW_ID = 1
_in_process_write_lock = threading.RLock()
_storage_backend_cache = None
_state_read_cache = None
_SUPABASE_READ_CACHE_TTL_SECONDS = 0.35


def _default_data():
    return {
        "odds": DEFAULT_ODDS,
        "accounts": {},
        "active_sessions": {},
        "game_limits": _default_game_limits(),
        "poker_lan": _default_poker_lan_state(),
    }


def _default_stats_bucket():
    return {
        "rounds_played": 0,
        "rounds_won": 0,
        "total_game_buy_in": 0.0,
        "total_game_payout": 0.0,
        "total_game_net": 0.0,
        "current_win_percentage": 0.0,
    }


def _default_account_stats():
    stats = _default_stats_bucket()
    stats["game_breakdown"] = {game_key: _default_stats_bucket() for game_key in GAME_STAT_KEYS}
    return stats


def _default_game_limits():
    return {
        "max_range": None,
        "max_buy_in": None,
        "max_guesses": None,
    }


def _default_account_settings():
    return {
        "allow_negative_balance": False,
        "dark_mode": True,
        "enable_animations": True,
        "confirm_before_bet": True,
        "profile_avatar": "",
    }


def _persist_if_changed_unlocked(data, before_data):
    if data != before_data:
        _write_data_unlocked(data)


def _normalize_stats_bucket(raw_stats):
    stats = _default_stats_bucket()
    if not isinstance(raw_stats, dict):
        return stats

    try:
        rounds_played = int(raw_stats.get("rounds_played", 0))
    except (TypeError, ValueError):
        rounds_played = 0
    try:
        rounds_won = int(raw_stats.get("rounds_won", 0))
    except (TypeError, ValueError):
        rounds_won = 0
    rounds_played = max(0, rounds_played)
    rounds_won = max(0, min(rounds_won, rounds_played))

    stats["rounds_played"] = rounds_played
    stats["rounds_won"] = rounds_won
    try:
        stats["total_game_buy_in"] = house_round_balance(raw_stats.get("total_game_buy_in", 0.0))
    except Exception:
        stats["total_game_buy_in"] = 0.0
    try:
        stats["total_game_payout"] = house_round_balance(raw_stats.get("total_game_payout", 0.0))
    except Exception:
        stats["total_game_payout"] = 0.0
    try:
        stats["total_game_net"] = house_round_balance(raw_stats.get("total_game_net", 0.0))
    except Exception:
        stats["total_game_net"] = 0.0

    if rounds_played > 0:
        computed_percentage = (rounds_won / rounds_played) * 100.0
    else:
        computed_percentage = 0.0
    try:
        saved_percentage = float(raw_stats.get("current_win_percentage", computed_percentage))
    except (TypeError, ValueError):
        saved_percentage = computed_percentage
    if saved_percentage < 0:
        saved_percentage = 0.0
    if saved_percentage > 100:
        saved_percentage = 100.0
    stats["current_win_percentage"] = computed_percentage if rounds_played > 0 else saved_percentage
    return stats


def _normalize_account_stats(raw_stats):
    stats = _normalize_stats_bucket(raw_stats)
    breakdown = {game_key: _default_stats_bucket() for game_key in GAME_STAT_KEYS}
    if isinstance(raw_stats, dict):
        raw_breakdown = raw_stats.get("game_breakdown", {})
        if isinstance(raw_breakdown, dict):
            for game_key in GAME_STAT_KEYS:
                breakdown[game_key] = _normalize_stats_bucket(raw_breakdown.get(game_key, {}))
    stats["game_breakdown"] = breakdown
    return stats


def _normalize_account_settings(raw_settings):
    settings = _default_account_settings()
    if not isinstance(raw_settings, dict):
        return settings

    # Backward compatibility for old saved data that used confetti_on_win.
    if "enable_animations" in raw_settings:
        settings["enable_animations"] = bool(raw_settings.get("enable_animations"))
    elif "confetti_on_win" in raw_settings:
        settings["enable_animations"] = bool(raw_settings.get("confetti_on_win"))

    settings["allow_negative_balance"] = bool(
        raw_settings.get("allow_negative_balance", settings["allow_negative_balance"])
    )
    settings["dark_mode"] = bool(raw_settings.get("dark_mode", settings["dark_mode"]))
    settings["confirm_before_bet"] = bool(raw_settings.get("confirm_before_bet", settings["confirm_before_bet"]))
    avatar_value = raw_settings.get("profile_avatar", settings["profile_avatar"])
    if avatar_value is None:
        avatar_value = ""
    settings["profile_avatar"] = str(avatar_value).strip()
    return settings


def _normalize_session_id(raw_value):
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    return normalized


def _normalize_session_timestamp(raw_value):
    try:
        normalized = float(raw_value)
    except (TypeError, ValueError):
        return None
    if normalized <= 0:
        return None
    return normalized


def _normalize_active_sessions(raw_sessions, account_names):
    normalized = {}
    if not isinstance(raw_sessions, dict):
        return normalized

    for account_name, raw_entry in raw_sessions.items():
        if account_name not in account_names:
            continue
        if not isinstance(raw_entry, dict):
            continue
        session_id = _normalize_session_id(raw_entry.get("session_id"))
        if session_id is None:
            continue
        last_seen = _normalize_session_timestamp(
            raw_entry.get("last_seen_epoch", raw_entry.get("last_seen"))
        )
        if last_seen is None:
            continue
        normalized[account_name] = {"session_id": session_id, "last_seen_epoch": last_seen}
    return normalized


def _coerce_session_ttl_seconds(ttl_seconds):
    try:
        ttl = int(ttl_seconds)
    except (TypeError, ValueError):
        ttl = DEFAULT_ACCOUNT_SESSION_TTL_SECONDS
    return max(1, ttl)


def _prune_expired_sessions_unlocked(data, now_epoch, ttl_seconds):
    account_names = set(data.get("accounts", {}).keys())
    raw_sessions = data.get("active_sessions", {})
    normalized_sessions = _normalize_active_sessions(raw_sessions, account_names)
    pruned_sessions = {}
    for account_name, session_entry in normalized_sessions.items():
        last_seen = float(session_entry["last_seen_epoch"])
        if now_epoch - last_seen > ttl_seconds:
            continue
        pruned_sessions[account_name] = session_entry
    data["active_sessions"] = pruned_sessions


def _load_streamlit_secret(name):
    try:
        import streamlit as st
    except Exception:
        return None
    try:
        value = st.secrets.get(name)
    except Exception:
        return None
    if value is None:
        return None
    return str(value).strip()


def _resolve_secret(name):
    import os
    value = os.getenv(name)
    if value is not None and str(value).strip():
        return str(value).strip()
    return _load_streamlit_secret(name)


def _get_storage_backend():
    global _storage_backend_cache
    if _storage_backend_cache is not None:
        return _storage_backend_cache

    supabase_url = _resolve_secret("SUPABASE_URL")
    supabase_key = (
        _resolve_secret("SUPABASE_SERVICE_ROLE_KEY")
        or _resolve_secret("SUPABASE_KEY")
        or _resolve_secret("SUPABASE_ANON_KEY")
    )
    supabase_table = _resolve_secret("SUPABASE_TABLE") or SUPABASE_TABLE_DEFAULT

    if supabase_url and supabase_key:
        _storage_backend_cache = {
            "type": "supabase",
            "url": supabase_url.rstrip("/"),
            "key": supabase_key,
            "table": supabase_table,
        }
    else:
        raise RuntimeError("Supabase is not configured. Account storage is unavailable.")
    return _storage_backend_cache


def _invalidate_state_read_cache():
    global _state_read_cache
    _state_read_cache = None


def _is_cached_state_valid_unlocked(backend):
    if not isinstance(_state_read_cache, dict):
        return False
    cached_backend_type = _state_read_cache.get("backend_type")
    backend_type = backend.get("type")
    if cached_backend_type != backend_type:
        return False
    if backend_type == "supabase":
        loaded_epoch = float(_state_read_cache.get("loaded_epoch", 0.0))
        return (time.time() - loaded_epoch) <= _SUPABASE_READ_CACHE_TTL_SECONDS
    return False


def _set_state_read_cache_unlocked(backend, data):
    global _state_read_cache
    backend_type = backend.get("type")
    _state_read_cache = {
        "backend_type": backend_type,
        "loaded_epoch": time.time(),
        "local_mtime": None,
        "data": deepcopy(data),
    }


def _supabase_request(method, path, payload=None, extra_headers=None):
    backend = _get_storage_backend()
    if backend.get("type") != "supabase":
        raise RuntimeError("Supabase request attempted without Supabase backend configuration.")

    url = f"{backend['url']}{path}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    headers = {
        "apikey": backend["key"],
        "Authorization": f"Bearer {backend['key']}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    request = urllib_request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib_request.urlopen(request, timeout=15) as response:
            raw = response.read()
    except urllib_error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase request failed ({exc.code}): {details}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Supabase request failed: {exc.reason}") from exc

    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _read_supabase_state_unlocked():
    backend = _get_storage_backend()
    table = backend["table"]
    query = urllib_parse.urlencode({"id": f"eq.{SUPABASE_STATE_ROW_ID}", "select": "data"})
    rows = _supabase_request("GET", f"/rest/v1/{table}?{query}")
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    if not isinstance(row, dict):
        return None
    state = row.get("data")
    if isinstance(state, dict):
        return state
    return None


def _write_supabase_state_unlocked(data):
    backend = _get_storage_backend()
    table = backend["table"]
    payload = [{"id": SUPABASE_STATE_ROW_ID, "data": data}]
    _supabase_request(
        "POST",
        f"/rest/v1/{table}?on_conflict=id",
        payload=payload,
        extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
    )


@contextmanager
def _accounts_write_lock():
    _get_storage_backend()
    with _in_process_write_lock:
        yield


def _write_data_unlocked(data):
    _get_storage_backend()
    _write_supabase_state_unlocked(data)
    _invalidate_state_read_cache()


def _write_data(data):
    with _accounts_write_lock():
        _write_data_unlocked(data)


def _account_from_raw(raw_account):
    if not isinstance(raw_account, dict):
        return None
    balance = raw_account.get("balance")
    password = raw_account.get("password", "")
    stats = _normalize_account_stats(raw_account.get("stats", {}))
    is_admin = bool(raw_account.get("is_admin", False))
    settings = _normalize_account_settings(raw_account.get("settings", {}))
    try:
        balance = house_round_balance(float(balance))
    except (TypeError, ValueError):
        return None
    if not isinstance(password, str):
        password = str(password)
    return {
        "balance": balance,
        "password": password,
        "stats": stats,
        "is_admin": is_admin,
        "settings": settings,
    }


def _normalize_loaded_data(loaded):
    if not isinstance(loaded, dict):
        raise ValueError("State root must be an object.")

    data = _default_data()

    saved_odds = loaded.get("odds", DEFAULT_ODDS)
    try:
        saved_odds = float(saved_odds)
    except (TypeError, ValueError):
        saved_odds = DEFAULT_ODDS
    if saved_odds > 0:
        data["odds"] = saved_odds

    raw_accounts = loaded.get("accounts", {})
    if isinstance(raw_accounts, dict):
        for name, raw_account in raw_accounts.items():
            if not isinstance(name, str):
                continue
            normalized_account = _account_from_raw(raw_account)
            if normalized_account is None:
                continue
            data["accounts"][name] = normalized_account
    data["active_sessions"] = _normalize_active_sessions(
        loaded.get("active_sessions", {}),
        set(data["accounts"].keys()),
    )

    raw_limits = loaded.get("game_limits")
    if isinstance(raw_limits, dict):
        limits = _default_game_limits()
        try:
            max_range = raw_limits.get("max_range")
            if max_range is not None:
                max_range = int(max_range)
                if max_range > 0:
                    limits["max_range"] = max_range
        except (TypeError, ValueError):
            pass
        try:
            max_buy_in = raw_limits.get("max_buy_in")
            if max_buy_in is not None:
                max_buy_in = float(max_buy_in)
                if max_buy_in > 0:
                    limits["max_buy_in"] = max_buy_in
        except (TypeError, ValueError):
            pass
        try:
            max_guesses = raw_limits.get("max_guesses")
            if max_guesses is not None:
                max_guesses = int(max_guesses)
                if max_guesses > 0:
                    limits["max_guesses"] = max_guesses
        except (TypeError, ValueError):
            pass
        data["game_limits"] = limits

    data["poker_lan"] = _normalize_poker_lan_state(loaded.get("poker_lan", {}))
    return data


def _load_data_unlocked(use_cache=True):
    backend = _get_storage_backend()
    if use_cache and _is_cached_state_valid_unlocked(backend):
        # Return the cached normalized state directly to avoid repeatedly
        # deep-copying the full app state on every read helper call.
        return _state_read_cache.get("data")
    try:
        loaded = _read_supabase_state_unlocked()
        if loaded is None:
            _set_state_read_cache_unlocked(backend, None)
            return None
        normalized = _normalize_loaded_data(loaded)
        _set_state_read_cache_unlocked(backend, normalized)
        return normalized
    except (json.JSONDecodeError, ValueError):
        _set_state_read_cache_unlocked(backend, None)
        return None


def _load_data():
    data = _load_data_unlocked(use_cache=True)
    if data is None:
        return _default_data()
    return data


def _load_data_for_write_unlocked():
    data = _load_data_unlocked(use_cache=False)
    if data is None:
        return _default_data()
    return data


def load_saved_odds():
    # Load saved house odds from persistent JSON, falling back to default.
    data = _load_data()
    saved = data.get("odds", DEFAULT_ODDS)
    return saved if saved > 0 else DEFAULT_ODDS


def save_odds(value):
    # Persist house odds in JSON storage.
    new_value = float(value)
    if new_value <= 0:
        return
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        data["odds"] = new_value
        _write_data_unlocked(data)


def load_game_limits():
    # Load saved game limits from persistent JSON, falling back to defaults.
    data = _load_data()
    saved = data.get("game_limits", _default_game_limits())
    normalized = _default_game_limits()
    
    # Normalize max_range
    try:
        max_range = saved.get("max_range")
        if max_range is not None:
            max_range = int(max_range)
            if max_range > 0:
                normalized["max_range"] = max_range
    except (TypeError, ValueError):
        pass
    
    # Normalize max_buy_in
    try:
        max_buy_in = saved.get("max_buy_in")
        if max_buy_in is not None:
            max_buy_in = float(max_buy_in)
            if max_buy_in > 0:
                normalized["max_buy_in"] = max_buy_in
    except (TypeError, ValueError):
        pass
    
    # Normalize max_guesses
    try:
        max_guesses = saved.get("max_guesses")
        if max_guesses is not None:
            max_guesses = int(max_guesses)
            if max_guesses > 0:
                normalized["max_guesses"] = max_guesses
    except (TypeError, ValueError):
        pass
    
    return normalized


def save_game_limits(max_range, max_buy_in, max_guesses):
    # Persist game limits in JSON storage.
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        limits = _default_game_limits()
        
        # Validate and set max_range
        if max_range is not None:
            try:
                max_range = int(max_range)
                if max_range > 0:
                    limits["max_range"] = max_range
            except (TypeError, ValueError):
                pass
        
        # Validate and set max_buy_in
        if max_buy_in is not None:
            try:
                max_buy_in = float(max_buy_in)
                if max_buy_in > 0:
                    limits["max_buy_in"] = max_buy_in
            except (TypeError, ValueError):
                pass
        
        # Validate and set max_guesses
        if max_guesses is not None:
            try:
                max_guesses = int(max_guesses)
                if max_guesses > 0:
                    limits["max_guesses"] = max_guesses
            except (TypeError, ValueError):
                pass
        
        data["game_limits"] = limits
        _write_data_unlocked(data)


def is_reserved_account_name(name):
    # Reserved names are internal and cannot be used as normal accounts.
    return name == ODDS_ACCOUNT_KEY


def get_account_value(name):
    # Return account balance by name; None if not found.
    data = _load_data()
    account = data["accounts"].get(name)
    if account is None:
        return None
    return account["balance"]


def get_account_password(name):
    # Return stored password for an account; empty string means no password set.
    data = _load_data()
    account = data["accounts"].get(name)
    if account is None:
        return None
    return account.get("password", "")


def set_account_password(name, password):
    # Persist password for an existing account.
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        account = data["accounts"].get(name)
        if account is None:
            return False
        account["password"] = password
        _write_data_unlocked(data)
        return True


def add_account_value(name, amount):
    # Add (or subtract) value from one account and persist file.
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        account = data["accounts"].get(name)
        if account is None:
            return False
        delta = house_round_delta(amount)
        account["balance"] = house_round_balance(account["balance"] + delta)
        _write_data_unlocked(data)
        return True


def list_account_names():
    data = _load_data()
    return [name for name in data["accounts"] if not is_reserved_account_name(name)]


def set_account_value(name, new_balance):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        account = data["accounts"].get(name)
        if account is None:
            return False, 0.0
        normalized_balance = house_round_balance(new_balance)
        account["balance"] = normalized_balance
        _write_data_unlocked(data)
        return True, float(normalized_balance)


def create_account_record(name, initial_balance, password=""):
    if is_reserved_account_name(name):
        return False
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        if name in data["accounts"]:
            return False
        data["accounts"][name] = {
            "balance": house_round_credit(initial_balance),
            "password": password,
            "stats": _default_account_stats(),
            "is_admin": False,
            "settings": _default_account_settings(),
        }
        _write_data_unlocked(data)
        return True


def get_account_admin_status(name):
    data = _load_data()
    account = data["accounts"].get(name)
    if account is None:
        return None
    return bool(account.get("is_admin", False))


def set_account_admin_status(name, is_admin):
    if is_reserved_account_name(name):
        return False
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        account = data["accounts"].get(name)
        if account is None:
            return False
        account["is_admin"] = bool(is_admin)
        _write_data_unlocked(data)
        return True


def delete_account(name):
    if is_reserved_account_name(name):
        return False
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        if name not in data["accounts"]:
            return False
        del data["accounts"][name]
        sessions = data.setdefault("active_sessions", {})
        sessions.pop(name, None)
        poker_lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        _poker_remove_player_from_all_tables_unlocked(data, poker_lan_state, name, allow_in_hand=True)
        data["poker_lan"] = poker_lan_state
        _write_data_unlocked(data)
        return True


def acquire_account_session(name, session_id, ttl_seconds=DEFAULT_ACCOUNT_SESSION_TTL_SECONDS):
    normalized_session_id = _normalize_session_id(session_id)
    if normalized_session_id is None:
        return False, "invalid_session"

    ttl = _coerce_session_ttl_seconds(ttl_seconds)
    now_epoch = time.time()

    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        if name not in data["accounts"]:
            return False, "account_not_found"

        _prune_expired_sessions_unlocked(data, now_epoch, ttl)
        sessions = data.setdefault("active_sessions", {})
        existing_entry = sessions.get(name)
        if isinstance(existing_entry, dict):
            existing_session_id = _normalize_session_id(existing_entry.get("session_id"))
            if existing_session_id is not None and existing_session_id != normalized_session_id:
                return False, "in_use"

        sessions[name] = {"session_id": normalized_session_id, "last_seen_epoch": now_epoch}
        _write_data_unlocked(data)
        return True, "acquired"


def force_acquire_account_session(name, session_id):
    normalized_session_id = _normalize_session_id(session_id)
    if normalized_session_id is None:
        return False, "invalid_session"

    now_epoch = time.time()
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        if name not in data["accounts"]:
            return False, "account_not_found"
        sessions = data.setdefault("active_sessions", {})
        sessions[name] = {"session_id": normalized_session_id, "last_seen_epoch": now_epoch}
        _write_data_unlocked(data)
        return True, "acquired"


def release_account_session(name, session_id):
    normalized_session_id = _normalize_session_id(session_id)
    if normalized_session_id is None:
        return False

    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        sessions = data.setdefault("active_sessions", {})
        existing_entry = sessions.get(name)
        if not isinstance(existing_entry, dict):
            return True

        existing_session_id = _normalize_session_id(existing_entry.get("session_id"))
        if existing_session_id != normalized_session_id:
            return False

        del sessions[name]
        _write_data_unlocked(data)
        return True


def _normalize_game_type(game_type):
    if isinstance(game_type, str):
        normalized = game_type.strip().lower()
        if normalized in GAME_STAT_KEYS:
            return normalized
    return None


def get_account_stats(name, game_type=None):
    data = _load_data()
    account = data["accounts"].get(name)
    if account is None:
        return None
    stats = _normalize_account_stats(account.get("stats", {}))
    selected_game_type = _normalize_game_type(game_type)
    if selected_game_type is None:
        return stats
    return _normalize_stats_bucket(stats.get("game_breakdown", {}).get(selected_game_type, {}))


def get_storage_backend_type():
    backend = _get_storage_backend()
    return str(backend.get("type", "local"))


def get_accounts_snapshot(game_type=None):
    data = _load_data()
    selected_game_type = _normalize_game_type(game_type)
    snapshot = {}
    for name, account in data["accounts"].items():
        if is_reserved_account_name(name):
            continue
        if not isinstance(account, dict):
            continue
        try:
            balance = house_round_balance(float(account.get("balance", 0.0)))
        except (TypeError, ValueError):
            balance = 0.0
        account_stats = _normalize_account_stats(account.get("stats", {}))
        if selected_game_type is None:
            scoped_stats = _normalize_stats_bucket(account_stats)
        else:
            scoped_stats = _normalize_stats_bucket(
                account_stats.get("game_breakdown", {}).get(selected_game_type, {})
            )
        snapshot[name] = {
            "balance": float(balance),
            "stats": scoped_stats,
        }
    return snapshot


def get_account_settings(name):
    data = _load_data()
    account = data["accounts"].get(name)
    if account is None:
        return None
    return _normalize_account_settings(account.get("settings", {}))


def set_account_settings(name, settings):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        account = data["accounts"].get(name)
        if account is None:
            return False
        account["settings"] = _normalize_account_settings(settings)
        _write_data_unlocked(data)
        return True


def _apply_result_to_stats_bucket(stats, buy_in, payout, won):
    buy_in_value = house_round_delta(buy_in)
    payout_value = house_round_delta(payout)
    net_value = house_round_balance(payout_value - buy_in_value)

    stats["rounds_played"] += 1
    if won:
        stats["rounds_won"] += 1
    stats["total_game_buy_in"] = house_round_balance(stats["total_game_buy_in"] + buy_in_value)
    stats["total_game_payout"] = house_round_balance(stats["total_game_payout"] + payout_value)
    stats["total_game_net"] = house_round_balance(stats["total_game_net"] + net_value)

    if stats["rounds_played"] > 0:
        stats["current_win_percentage"] = (stats["rounds_won"] / stats["rounds_played"]) * 100.0
    else:
        stats["current_win_percentage"] = 0.0


def record_game_result(name, buy_in, payout, won, game_type=None):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        account = data["accounts"].get(name)
        if account is None:
            return False

        stats = _normalize_account_stats(account.get("stats", {}))
        _apply_result_to_stats_bucket(stats, buy_in, payout, won)
        selected_game_type = _normalize_game_type(game_type)
        if selected_game_type is not None:
            breakdown = stats.get("game_breakdown", {})
            game_stats = _normalize_stats_bucket(breakdown.get(selected_game_type, {}))
            _apply_result_to_stats_bucket(game_stats, buy_in, payout, won)
            breakdown[selected_game_type] = game_stats
            stats["game_breakdown"] = breakdown

        account["stats"] = stats
        _write_data_unlocked(data)
        return True


POKER_LAN_DEFAULT_TABLE_COUNT = 0
POKER_LAN_DEFAULT_MAX_PLAYERS = 6
POKER_LAN_DEFAULT_MIN_BUY_IN = 40.0
POKER_LAN_DEFAULT_MAX_BUY_IN = 400.0
POKER_LAN_DEFAULT_SMALL_BLIND = 1.0
POKER_LAN_DEFAULT_BIG_BLIND = 2.0
POKER_LAN_DEFAULT_MIN_RAISE = 0.01
POKER_LAN_MAX_BOTS_PER_TABLE = 3
POKER_LAN_DEFAULT_TURN_TIMEOUT_SECONDS = 30
POKER_LAN_PHASE_WAITING = "waiting_ready"
POKER_LAN_PHASE_IN_HAND = "in_hand"
POKER_LAN_PHASE_FINISHED = "finished"


def _default_poker_lan_settings():
    return {
        "default_max_players": POKER_LAN_DEFAULT_MAX_PLAYERS,
        "default_min_buy_in": POKER_LAN_DEFAULT_MIN_BUY_IN,
        "default_max_buy_in": POKER_LAN_DEFAULT_MAX_BUY_IN,
        "default_small_blind": POKER_LAN_DEFAULT_SMALL_BLIND,
        "default_big_blind": POKER_LAN_DEFAULT_BIG_BLIND,
        "default_min_raise": POKER_LAN_DEFAULT_MIN_RAISE,
        "allow_spectators_by_default": True,
        "turn_timeout_seconds": POKER_LAN_DEFAULT_TURN_TIMEOUT_SECONDS,
    }


def _coerce_poker_currency(raw_value, fallback, allow_none=False):
    if allow_none and raw_value is None:
        return None
    try:
        normalized = house_round_credit(float(raw_value))
    except Exception:
        normalized = house_round_credit(float(fallback))
    if normalized < 0:
        return 0.0
    return float(normalized)


def _coerce_poker_turn_timeout(raw_value, fallback):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        try:
            value = int(fallback)
        except (TypeError, ValueError):
            value = POKER_LAN_DEFAULT_TURN_TIMEOUT_SECONDS
    return max(5, value)


def _normalize_poker_lan_settings(raw_settings):
    settings = _default_poker_lan_settings()
    if not isinstance(raw_settings, dict):
        return settings
    settings["default_max_players"] = max(2, min(6, int(raw_settings.get("default_max_players", settings["default_max_players"]))))
    settings["default_min_buy_in"] = _coerce_poker_currency(
        raw_settings.get("default_min_buy_in", settings["default_min_buy_in"]),
        settings["default_min_buy_in"],
    )
    settings["default_max_buy_in"] = _coerce_poker_currency(
        raw_settings.get("default_max_buy_in", settings["default_max_buy_in"]),
        settings["default_max_buy_in"],
    )
    if settings["default_max_buy_in"] < settings["default_min_buy_in"]:
        settings["default_max_buy_in"] = settings["default_min_buy_in"]
    settings["default_small_blind"] = max(
        0.01,
        _coerce_poker_currency(raw_settings.get("default_small_blind", settings["default_small_blind"]), settings["default_small_blind"]),
    )
    settings["default_big_blind"] = max(
        settings["default_small_blind"],
        _coerce_poker_currency(raw_settings.get("default_big_blind", settings["default_big_blind"]), settings["default_big_blind"]),
    )
    settings["default_min_raise"] = max(
        0.01,
        _coerce_poker_currency(raw_settings.get("default_min_raise", settings["default_min_raise"]), settings["default_min_raise"]),
    )
    settings["allow_spectators_by_default"] = bool(
        raw_settings.get("allow_spectators_by_default", settings["allow_spectators_by_default"])
    )
    settings["turn_timeout_seconds"] = _coerce_poker_turn_timeout(
        raw_settings.get("turn_timeout_seconds", settings["turn_timeout_seconds"]),
        settings["turn_timeout_seconds"],
    )
    return settings


def _normalize_poker_lan_table_name(name, fallback_id):
    if not isinstance(name, str) or not name.strip():
        return f"Poker Table {int(fallback_id)}"
    return name.strip()[:60]


def _poker_bot_name(table_id, bot_index):
    return f"bot_{int(table_id)}_{int(bot_index)}"


def _poker_is_bot_name(player_name):
    text = str(player_name or "").strip().lower()
    return text.startswith("bot_")


def _poker_table_human_players(table):
    humans = []
    for name in table.get("players", []):
        text = str(name).strip()
        if not text or _poker_is_bot_name(text):
            continue
        humans.append(text)
    return humans


def _default_poker_lan_table(table_id, settings=None):
    normalized_settings = _normalize_poker_lan_settings(settings or {})
    return {
        "id": int(table_id),
        "name": _normalize_poker_lan_table_name(None, table_id),
        "host": None,
        "players": [],
        "pending_players": [],
        "bot_count": 0,
        "player_states": {},
        "max_players": int(normalized_settings["default_max_players"]),
        "min_buy_in": float(normalized_settings["default_min_buy_in"]),
        "max_buy_in": float(normalized_settings["default_max_buy_in"]),
        "small_blind": float(normalized_settings["default_small_blind"]),
        "big_blind": float(normalized_settings["default_big_blind"]),
        "min_raise": float(normalized_settings["default_min_raise"]),
        "allow_spectators": bool(normalized_settings["allow_spectators_by_default"]),
        "spectators_require_password": False,
        "is_private": False,
        "password": "",
        "phase": POKER_LAN_PHASE_WAITING,
        "in_progress": False,
        "round": 0,
        "dealer_index": 0,
        "hand_state": None,
        "hand_start_stacks": {},
        "turn_started_epoch": 0.0,
        "turn_timeout_seconds": int(normalized_settings["turn_timeout_seconds"]),
        "history": [],
        "last_updated_epoch": 0.0,
    }


def _normalize_poker_player_state(raw_state):
    state = {
        "stack_cents": 0,
        "ready": False,
        "last_hand_delta_cents": 0,
    }
    if isinstance(raw_state, dict):
        try:
            state["stack_cents"] = max(0, int(raw_state.get("stack_cents", 0)))
        except (TypeError, ValueError):
            state["stack_cents"] = 0
        state["ready"] = bool(raw_state.get("ready", False))
        try:
            state["last_hand_delta_cents"] = int(raw_state.get("last_hand_delta_cents", 0))
        except (TypeError, ValueError):
            state["last_hand_delta_cents"] = 0
    return state


def _normalize_poker_lan_table(raw_table, fallback_id, settings=None):
    table = _default_poker_lan_table(fallback_id, settings=settings)
    if not isinstance(raw_table, dict):
        return table
    try:
        table["id"] = int(raw_table.get("id", fallback_id))
    except (TypeError, ValueError):
        table["id"] = int(fallback_id)
    table["name"] = _normalize_poker_lan_table_name(raw_table.get("name"), table["id"])
    table["host"] = raw_table.get("host") if isinstance(raw_table.get("host"), str) else None
    raw_players = raw_table.get("players", [])
    if isinstance(raw_players, list):
        table["players"] = [str(name).strip() for name in raw_players if str(name).strip()][: int(table["max_players"])]
    raw_pending = raw_table.get("pending_players", [])
    if isinstance(raw_pending, list):
        table["pending_players"] = [str(name).strip() for name in raw_pending if str(name).strip()]
    try:
        table["max_players"] = max(2, min(6, int(raw_table.get("max_players", table["max_players"]))))
    except (TypeError, ValueError):
        pass
    try:
        max_bots = min(POKER_LAN_MAX_BOTS_PER_TABLE, max(0, int(table["max_players"]) - 1))
        table["bot_count"] = max(0, min(max_bots, int(raw_table.get("bot_count", table.get("bot_count", 0)))))
    except (TypeError, ValueError):
        table["bot_count"] = 0
    table["min_buy_in"] = _coerce_poker_currency(raw_table.get("min_buy_in", table["min_buy_in"]), table["min_buy_in"])
    table["max_buy_in"] = _coerce_poker_currency(raw_table.get("max_buy_in", table["max_buy_in"]), table["max_buy_in"])
    if table["max_buy_in"] < table["min_buy_in"]:
        table["max_buy_in"] = table["min_buy_in"]
    table["small_blind"] = max(
        0.01,
        _coerce_poker_currency(raw_table.get("small_blind", table["small_blind"]), table["small_blind"]),
    )
    table["big_blind"] = max(
        table["small_blind"],
        _coerce_poker_currency(raw_table.get("big_blind", table["big_blind"]), table["big_blind"]),
    )
    table["min_raise"] = max(
        0.01,
        _coerce_poker_currency(raw_table.get("min_raise", table["min_raise"]), table["min_raise"]),
    )
    table["allow_spectators"] = bool(raw_table.get("allow_spectators", table["allow_spectators"]))
    table["spectators_require_password"] = bool(
        raw_table.get("spectators_require_password", table["spectators_require_password"])
    )
    table["is_private"] = bool(raw_table.get("is_private", table["is_private"]))
    table["password"] = str(raw_table.get("password", "") or "")
    table["phase"] = str(raw_table.get("phase", table["phase"]))
    table["in_progress"] = bool(raw_table.get("in_progress", table["in_progress"]))
    try:
        table["round"] = max(0, int(raw_table.get("round", table["round"])))
    except (TypeError, ValueError):
        pass
    try:
        table["dealer_index"] = max(0, int(raw_table.get("dealer_index", table["dealer_index"])))
    except (TypeError, ValueError):
        pass
    if isinstance(raw_table.get("hand_state"), dict):
        table["hand_state"] = raw_table.get("hand_state")
    if isinstance(raw_table.get("hand_start_stacks"), dict):
        normalized_stacks = {}
        for name, value in raw_table.get("hand_start_stacks", {}).items():
            if not isinstance(name, str):
                continue
            try:
                normalized_stacks[str(name)] = int(value)
            except (TypeError, ValueError):
                continue
        table["hand_start_stacks"] = normalized_stacks
    try:
        table["turn_started_epoch"] = float(raw_table.get("turn_started_epoch", table["turn_started_epoch"]))
    except (TypeError, ValueError):
        pass
    table["turn_timeout_seconds"] = _coerce_poker_turn_timeout(
        raw_table.get("turn_timeout_seconds", table["turn_timeout_seconds"]),
        table["turn_timeout_seconds"],
    )
    if isinstance(raw_table.get("history"), list):
        table["history"] = [str(entry) for entry in raw_table.get("history", []) if isinstance(entry, str)][-40:]
    try:
        table["last_updated_epoch"] = float(raw_table.get("last_updated_epoch", table["last_updated_epoch"]))
    except (TypeError, ValueError):
        pass

    raw_states = raw_table.get("player_states", {})
    normalized_states = {}
    if isinstance(raw_states, dict):
        for player_name in table["players"]:
            normalized_states[player_name] = _normalize_poker_player_state(raw_states.get(player_name, {}))
    for player_name in table["players"]:
        normalized_states.setdefault(player_name, _normalize_poker_player_state({}))
    table["player_states"] = normalized_states
    for player_name in table["players"]:
        if _poker_is_bot_name(player_name):
            table["player_states"][player_name]["ready"] = True
    actual_bot_count = sum(1 for name in table.get("players", []) if _poker_is_bot_name(name))
    max_bots = min(POKER_LAN_MAX_BOTS_PER_TABLE, max(0, int(table.get("max_players", 6)) - 1))
    table["bot_count"] = max(0, min(max_bots, actual_bot_count))

    if table["host"] not in table["players"] or _poker_is_bot_name(table["host"]):
        humans = _poker_table_human_players(table)
        table["host"] = humans[0] if humans else None

    return table


def _default_poker_lan_state():
    settings = _default_poker_lan_settings()
    return {
        "settings": settings,
        "tables": [_default_poker_lan_table(index + 1, settings=settings) for index in range(POKER_LAN_DEFAULT_TABLE_COUNT)],
    }


def _normalize_poker_lan_state(raw_state):
    state = _default_poker_lan_state()
    if not isinstance(raw_state, dict):
        return state
    settings = _normalize_poker_lan_settings(raw_state.get("settings", {}))
    state["settings"] = settings
    raw_tables = raw_state.get("tables", [])
    normalized_tables = []
    if isinstance(raw_tables, list):
        for index, raw_table in enumerate(raw_tables):
            normalized_tables.append(_normalize_poker_lan_table(raw_table, index + 1, settings=settings))
    if not normalized_tables:
        normalized_tables = [_default_poker_lan_table(index + 1, settings=settings) for index in range(POKER_LAN_DEFAULT_TABLE_COUNT)]
    by_id = {}
    for table in normalized_tables:
        by_id[int(table["id"])] = table
    state["tables"] = sorted(by_id.values(), key=lambda item: int(item.get("id", 0)))
    return state


def _poker_lan_next_table_id(lan_state):
    max_id = 0
    for table in lan_state.get("tables", []):
        try:
            max_id = max(max_id, int(table.get("id", 0)))
        except (TypeError, ValueError):
            pass
    return max_id + 1


def _poker_lan_table_by_id(lan_state, table_id):
    try:
        normalized_id = int(table_id)
    except (TypeError, ValueError):
        return None
    for table in lan_state.get("tables", []):
        if int(table.get("id", -1)) == normalized_id:
            return table
    return None


def _poker_lan_table_member_state(table, player_name):
    if player_name in table.get("players", []):
        return "player"
    if player_name in table.get("pending_players", []):
        return "pending"
    return None


def _poker_lan_append_history(table, message):
    history = table.setdefault("history", [])
    history.append(str(message))
    table["history"] = history[-40:]


def _poker_finalize_finished_hand_unlocked(data, table):
    hand_state = table.get("hand_state")
    if not isinstance(hand_state, dict):
        return
    if hand_state.get("street") != "finished":
        return

    players = hand_state.get("players", [])
    for player in players:
        player_name = player.get("name")
        if not isinstance(player_name, str):
            continue
        current_stack = int(player.get("stack", 0))
        table.setdefault("player_states", {}).setdefault(player_name, _normalize_poker_player_state({}))
        table["player_states"][player_name]["stack_cents"] = current_stack
        start_stack = int(table.get("hand_start_stacks", {}).get(player_name, current_stack))
        delta = current_stack - start_stack
        table["player_states"][player_name]["last_hand_delta_cents"] = delta
        account = data.get("accounts", {}).get(player_name)
        if not isinstance(account, dict):
            continue
        buy_in = from_cents(max(0, -delta))
        payout = from_cents(max(0, delta))
        won = delta > 0
        if buy_in > 0 or payout > 0:
            stats = _normalize_account_stats(account.get("stats", {}))
            _apply_result_to_stats_bucket(stats, buy_in, payout, won)
            breakdown = stats.get("game_breakdown", {})
            poker_stats = _normalize_stats_bucket(breakdown.get("poker", {}))
            _apply_result_to_stats_bucket(poker_stats, buy_in, payout, won)
            breakdown["poker"] = poker_stats
            stats["game_breakdown"] = breakdown
            account["stats"] = stats
    table["phase"] = POKER_LAN_PHASE_FINISHED
    table["in_progress"] = False


def _poker_run_bot_actions_unlocked(table):
    hand_state = table.get("hand_state")
    if not isinstance(hand_state, dict):
        return
    while hand_state.get("street") != "finished":
        acting_index = hand_state.get("acting_index")
        if not isinstance(acting_index, int):
            break
        players = hand_state.get("players", [])
        if acting_index < 0 or acting_index >= len(players):
            break
        acting_player = str(players[acting_index].get("name", "")).strip()
        if not acting_player or (not _poker_is_bot_name(acting_player)):
            break
        legal = poker_legal_actions(hand_state, acting_player)
        actions = legal.get("actions", [])
        if not actions:
            break
        action, amount = choose_bot_action(hand_state, acting_player, legal)
        ok, _message = poker_apply_action(hand_state, acting_player, action, amount)
        if not ok:
            poker_apply_action(hand_state, acting_player, "fold")
        _poker_lan_append_history(table, f"{acting_player}: {str(action).lower()}")
    table["hand_state"] = hand_state


def _poker_remove_player_from_all_tables_unlocked(data, lan_state, player_name, allow_in_hand=False):
    removed = False
    for table in lan_state.get("tables", []):
        if not isinstance(table, dict):
            continue
        membership = _poker_lan_table_member_state(table, player_name)
        if membership is None:
            continue
        if table.get("in_progress") and not allow_in_hand and membership == "player":
            continue
        removed = True
        if membership == "pending":
            table["pending_players"] = [name for name in table.get("pending_players", []) if name != player_name]
            table["last_updated_epoch"] = time.time()
            continue

        try:
            stack_cents = int(table.get("player_states", {}).get(player_name, {}).get("stack_cents", 0))
        except (TypeError, ValueError):
            stack_cents = 0
        account = data.get("accounts", {}).get(player_name)
        if stack_cents > 0 and isinstance(account, dict):
            account["balance"] = house_round_balance(account.get("balance", 0.0) + from_cents(stack_cents))

        table["players"] = [name for name in table.get("players", []) if name != player_name]
        table.get("player_states", {}).pop(player_name, None)
        if table.get("host") == player_name:
            humans = _poker_table_human_players(table)
            table["host"] = humans[0] if humans else None

        if table.get("in_progress") and isinstance(table.get("hand_state"), dict):
            for hand_player in table["hand_state"].get("players", []):
                if hand_player.get("name") == player_name:
                    hand_player["folded"] = True
                    hand_player["all_in"] = True
            _poker_lan_append_history(table, f"{player_name} left during an active hand and was folded.")
            _poker_run_bot_actions_unlocked(table)
            hand_state = table.get("hand_state")
            if isinstance(hand_state, dict) and hand_state.get("street") == "finished":
                _poker_finalize_finished_hand_unlocked(data, table)

        if not table.get("players", []):
            reset = _default_poker_lan_table(table.get("id", 1), settings=lan_state.get("settings", {}))
            reset["name"] = _normalize_poker_lan_table_name(table.get("name"), table.get("id", 1))
            table.clear()
            table.update(reset)
        else:
            table["last_updated_epoch"] = time.time()
    return removed


def get_poker_lan_tables():
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        before_data = deepcopy(data)
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        data["poker_lan"] = lan_state
        _persist_if_changed_unlocked(data, before_data)
        return deepcopy(lan_state.get("tables", []))


def get_poker_lan_settings():
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        before_data = deepcopy(data)
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        data["poker_lan"] = lan_state
        _persist_if_changed_unlocked(data, before_data)
        return deepcopy(lan_state.get("settings", _default_poker_lan_settings()))


def can_spectate_poker_lan_table(table_id, password=""):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        before_data = deepcopy(data)
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        table = _poker_lan_table_by_id(lan_state, table_id)
        if table is None:
            return False, "Table not found."
        settings = _normalize_poker_lan_settings(lan_state.get("settings", {}))
        if not bool(settings.get("allow_spectators_by_default", True)):
            return False, "Spectating is disabled by admin settings."
        if not bool(table.get("allow_spectators", True)):
            return False, "Spectating is disabled for this table."
        requires_password = bool(table.get("is_private", False)) or bool(table.get("spectators_require_password", False))
        if requires_password and str(table.get("password", "")) != str(password or ""):
            return False, "Incorrect table password."
        data["poker_lan"] = lan_state
        _persist_if_changed_unlocked(data, before_data)
        return True, "Spectating allowed."


def find_poker_lan_table_for_player(player_name):
    if not isinstance(player_name, str) or not player_name.strip():
        return None
    normalized_player = player_name.strip()
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        before_data = deepcopy(data)
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        for table in lan_state.get("tables", []):
            membership = _poker_lan_table_member_state(table, normalized_player)
            if membership is not None:
                found = deepcopy(table)
                found["membership"] = membership
                data["poker_lan"] = lan_state
                _persist_if_changed_unlocked(data, before_data)
                return found
        data["poker_lan"] = lan_state
        _persist_if_changed_unlocked(data, before_data)
        return None


def create_poker_lan_table(
    max_players=None,
    min_buy_in=None,
    max_buy_in=None,
    small_blind=None,
    big_blind=None,
    min_raise=None,
    allow_spectators=None,
    spectators_require_password=None,
    is_private=None,
    password=None,
    table_name=None,
    turn_timeout_seconds=None,
    bot_count=0,
):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        settings = _normalize_poker_lan_settings(lan_state.get("settings", {}))
        table_id = _poker_lan_next_table_id(lan_state)
        table = _default_poker_lan_table(table_id, settings=settings)
        if max_players is not None:
            try:
                table["max_players"] = max(2, min(6, int(max_players)))
            except (TypeError, ValueError):
                pass
        if min_buy_in is not None:
            table["min_buy_in"] = _coerce_poker_currency(min_buy_in, table["min_buy_in"])
        if max_buy_in is not None:
            table["max_buy_in"] = _coerce_poker_currency(max_buy_in, table["max_buy_in"])
        if table["max_buy_in"] < table["min_buy_in"]:
            table["max_buy_in"] = table["min_buy_in"]
        if small_blind is not None:
            table["small_blind"] = max(0.01, _coerce_poker_currency(small_blind, table["small_blind"]))
        if big_blind is not None:
            table["big_blind"] = max(table["small_blind"], _coerce_poker_currency(big_blind, table["big_blind"]))
        if min_raise is not None:
            table["min_raise"] = max(0.01, _coerce_poker_currency(min_raise, table["min_raise"]))
        if allow_spectators is not None:
            table["allow_spectators"] = bool(allow_spectators)
        if spectators_require_password is not None:
            table["spectators_require_password"] = bool(spectators_require_password)
        if is_private is not None:
            table["is_private"] = bool(is_private)
        if password is not None:
            table["password"] = str(password)
        if table_name is not None:
            table["name"] = _normalize_poker_lan_table_name(table_name, table_id)
        if turn_timeout_seconds is not None:
            table["turn_timeout_seconds"] = _coerce_poker_turn_timeout(turn_timeout_seconds, table["turn_timeout_seconds"])
        try:
            max_bots = min(POKER_LAN_MAX_BOTS_PER_TABLE, max(0, int(table["max_players"]) - 1))
            normalized_bot_count = max(0, min(max_bots, int(bot_count)))
        except (TypeError, ValueError):
            normalized_bot_count = 0
        table["bot_count"] = normalized_bot_count
        if bool(table.get("is_private")) and (not str(table.get("password", "")).strip()):
            return False, "Private tables must have a password."
        if bool(table.get("spectators_require_password")) and (not str(table.get("password", "")).strip()):
            return False, "Tables requiring spectator password must define a password."

        lane = lan_state.setdefault("tables", [])
        for existing in lane:
            if _normalize_poker_lan_table_name(existing.get("name"), existing.get("id")) == table["name"]:
                return False, "A table with that name already exists."
        for bot_index in range(1, int(table.get("bot_count", 0)) + 1):
            bot_name = _poker_bot_name(table_id, bot_index)
            table.setdefault("players", []).append(bot_name)
            table.setdefault("player_states", {})[bot_name] = _normalize_poker_player_state(
                {"stack_cents": int(round(float(table.get("min_buy_in", 0.0)) * 100)), "ready": True}
            )
            _poker_lan_append_history(table, f"{bot_name} joined the table.")
        table["phase"] = POKER_LAN_PHASE_WAITING
        lane.append(table)
        lan_state["tables"] = sorted(lane, key=lambda item: int(item.get("id", 0)))
        data["poker_lan"] = lan_state
        _write_data_unlocked(data)
        return True, f"Created table: {table['name']}"


def delete_poker_lan_table(table_id):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        table = _poker_lan_table_by_id(lan_state, table_id)
        if table is None:
            return False, "Table not found."
        if bool(table.get("in_progress")):
            return False, "Cannot delete a table during an active hand."
        human_players = [name for name in table.get("players", []) if not _poker_is_bot_name(name)]
        if human_players or table.get("pending_players"):
            return False, "Cannot delete table while players are seated or queued."
        lan_state["tables"] = [entry for entry in lan_state.get("tables", []) if int(entry.get("id", -1)) != int(table_id)]
        data["poker_lan"] = lan_state
        _write_data_unlocked(data)
        return True, f"Deleted table {int(table_id)}."


def update_poker_lan_table_settings(
    table_id,
    max_players,
    min_buy_in,
    max_buy_in,
    small_blind,
    big_blind,
    min_raise,
    allow_spectators=None,
    spectators_require_password=None,
    is_private=None,
    password=None,
    table_name=None,
    turn_timeout_seconds=None,
):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        table = _poker_lan_table_by_id(lan_state, table_id)
        if table is None:
            return False, "Table not found."
        if bool(table.get("in_progress")):
            return False, "Cannot edit table during active hand."

        try:
            table["max_players"] = max(2, min(6, int(max_players)))
        except (TypeError, ValueError):
            pass
        table["min_buy_in"] = _coerce_poker_currency(min_buy_in, table["min_buy_in"])
        table["max_buy_in"] = _coerce_poker_currency(max_buy_in, table["max_buy_in"])
        table["small_blind"] = max(0.01, _coerce_poker_currency(small_blind, table["small_blind"]))
        table["big_blind"] = max(table["small_blind"], _coerce_poker_currency(big_blind, table["big_blind"]))
        table["min_raise"] = max(0.01, _coerce_poker_currency(min_raise, table["min_raise"]))
        if table["max_buy_in"] < table["min_buy_in"]:
            table["max_buy_in"] = table["min_buy_in"]

        if allow_spectators is not None:
            table["allow_spectators"] = bool(allow_spectators)
        if spectators_require_password is not None:
            table["spectators_require_password"] = bool(spectators_require_password)
        if is_private is not None:
            table["is_private"] = bool(is_private)
        if password is not None:
            table["password"] = str(password)
        if table_name is not None:
            table["name"] = _normalize_poker_lan_table_name(table_name, table_id)
        if turn_timeout_seconds is not None:
            table["turn_timeout_seconds"] = _coerce_poker_turn_timeout(turn_timeout_seconds, table["turn_timeout_seconds"])

        if bool(table.get("is_private")) and (not str(table.get("password", "")).strip()):
            return False, "Private tables must have a password."
        if bool(table.get("spectators_require_password")) and (not str(table.get("password", "")).strip()):
            return False, "Tables requiring spectator password must define a password."

        if len(table.get("players", [])) > int(table.get("max_players", 6)):
            return False, "Reduce player count before lowering max players."

        table["last_updated_epoch"] = time.time()
        data["poker_lan"] = lan_state
        _write_data_unlocked(data)
        return True, "Table settings updated."


def update_poker_lan_global_settings(turn_timeout_seconds, allow_spectators_by_default=None):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        settings = _normalize_poker_lan_settings(lan_state.get("settings", {}))
        settings["turn_timeout_seconds"] = _coerce_poker_turn_timeout(turn_timeout_seconds, settings["turn_timeout_seconds"])
        if allow_spectators_by_default is not None:
            settings["allow_spectators_by_default"] = bool(allow_spectators_by_default)
        lan_state["settings"] = settings
        data["poker_lan"] = lan_state
        _write_data_unlocked(data)
        return True, "Poker multiplayer settings updated."


def join_poker_lan_table(table_id, player_name, password="", buy_in=None):
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player."
    normalized_player = player_name.strip()
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        if normalized_player not in data.get("accounts", {}):
            return False, "You must be signed in to join."

        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        destination = _poker_lan_table_by_id(lan_state, table_id)
        if destination is None:
            return False, "Table not found."

        if bool(destination.get("is_private")):
            if str(destination.get("password", "")) != str(password or ""):
                return False, "Incorrect table password."

        for table in lan_state.get("tables", []):
            membership = _poker_lan_table_member_state(table, normalized_player)
            if membership is None:
                continue
            if int(table.get("id", -1)) == int(table_id):
                return True, "Already in this table."
            if bool(table.get("in_progress")):
                return False, "Leave your current active table before joining another."
            _poker_remove_player_from_all_tables_unlocked(data, lan_state, normalized_player, allow_in_hand=False)
            break

        if normalized_player in destination.get("players", []):
            data["poker_lan"] = lan_state
            _write_data_unlocked(data)
            return True, "Already in this table."

        seated_and_pending = len(destination.get("players", [])) + len(destination.get("pending_players", []))
        if seated_and_pending >= int(destination.get("max_players", 6)):
            return False, "Table is full."

        if buy_in is None:
            buy_in = destination.get("min_buy_in", POKER_LAN_DEFAULT_MIN_BUY_IN)
        normalized_buy_in = _coerce_poker_currency(buy_in, destination.get("min_buy_in", 0.01))
        if normalized_buy_in < float(destination.get("min_buy_in", 0.01)):
            return False, f"Minimum buy-in is ${float(destination.get('min_buy_in', 0.01)):.2f}."
        if normalized_buy_in > float(destination.get("max_buy_in", destination.get("min_buy_in", 0.01))):
            return False, f"Maximum buy-in is ${float(destination.get('max_buy_in', 0.01)):.2f}."

        account = data["accounts"].get(normalized_player, {})
        balance = house_round_balance(account.get("balance", 0.0))
        account_settings = _normalize_account_settings(account.get("settings", {}))
        if (not bool(account_settings.get("allow_negative_balance", False))) and balance < normalized_buy_in:
            return False, "Insufficient funds for buy-in."

        account["balance"] = house_round_balance(balance - normalized_buy_in)

        if bool(destination.get("in_progress")):
            destination.setdefault("pending_players", []).append(normalized_player)
            destination.setdefault("player_states", {})[normalized_player] = _normalize_poker_player_state(
                {"stack_cents": int(round(normalized_buy_in * 100))}
            )
            _poker_lan_append_history(destination, f"{normalized_player} queued for next hand.")
            data["poker_lan"] = lan_state
            _write_data_unlocked(data)
            return True, "Hand in progress. You are queued for next hand."

        destination.setdefault("players", []).append(normalized_player)
        destination.setdefault("player_states", {})[normalized_player] = _normalize_poker_player_state(
            {"stack_cents": int(round(normalized_buy_in * 100))}
        )
        if (not destination.get("host")) or _poker_is_bot_name(destination.get("host")):
            destination["host"] = normalized_player
        destination["phase"] = POKER_LAN_PHASE_WAITING
        destination["last_updated_epoch"] = time.time()
        _poker_lan_append_history(destination, f"{normalized_player} joined with ${normalized_buy_in:.2f}.")

        data["poker_lan"] = lan_state
        _write_data_unlocked(data)
        return True, f"Joined table {int(table_id)}."


def leave_poker_lan_table(table_id, player_name):
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player."
    normalized_player = player_name.strip()
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        table = _poker_lan_table_by_id(lan_state, table_id)
        if table is None:
            return False, "Table not found."

        membership = _poker_lan_table_member_state(table, normalized_player)
        if membership is None:
            return True, "You are not in this table."
        if membership == "player" and bool(table.get("in_progress")):
            return False, "Cannot leave while a hand is in progress."

        _poker_remove_player_from_all_tables_unlocked(data, lan_state, normalized_player, allow_in_hand=False)
        data["poker_lan"] = lan_state
        _write_data_unlocked(data)
        return True, f"Left table {int(table_id)}."


def auto_remove_poker_lan_player(player_name):
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player."
    normalized_player = player_name.strip()
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        removed = _poker_remove_player_from_all_tables_unlocked(data, lan_state, normalized_player, allow_in_hand=True)
        data["poker_lan"] = lan_state
        _write_data_unlocked(data)
        if removed:
            return True, "Player removed from poker multiplayer tables."
        return True, "Player was not in poker multiplayer tables."


def set_poker_lan_player_ready(table_id, player_name, ready=True):
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player.", False
    normalized_player = player_name.strip()
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        table = _poker_lan_table_by_id(lan_state, table_id)
        if table is None:
            return False, "Table not found.", False
        if normalized_player not in table.get("players", []):
            return False, "Join this table first.", False
        if bool(table.get("in_progress")):
            return False, "Hand already in progress.", False

        table.setdefault("player_states", {}).setdefault(normalized_player, _normalize_poker_player_state({}))
        table["player_states"][normalized_player]["ready"] = bool(ready)
        table["last_updated_epoch"] = time.time()

        if not bool(ready):
            table["phase"] = POKER_LAN_PHASE_WAITING
            data["poker_lan"] = lan_state
            _write_data_unlocked(data)
            return True, "You are no longer ready.", False

        seated_ready = [
            name
            for name in table.get("players", [])
            if (
                bool(table.get("player_states", {}).get(name, {}).get("ready", False))
                or _poker_is_bot_name(name)
            )
            and int(table.get("player_states", {}).get(name, {}).get("stack_cents", 0)) > 0
        ]
        seated_eligible = [
            name
            for name in table.get("players", [])
            if int(table.get("player_states", {}).get(name, {}).get("stack_cents", 0)) > 0
        ]

        if len(seated_eligible) >= 2 and len(seated_ready) == len(seated_eligible):
            start_index = int(table.get("dealer_index", 0))
            start_stacks = [
                (name, from_cents(int(table["player_states"][name]["stack_cents"]))) for name in seated_eligible
            ]
            hand_state, error = poker_create_hand(
                start_stacks,
                table.get("small_blind", POKER_LAN_DEFAULT_SMALL_BLIND),
                table.get("big_blind", POKER_LAN_DEFAULT_BIG_BLIND),
                min_raise=table.get("min_raise", POKER_LAN_DEFAULT_MIN_RAISE),
                dealer_index=max(0, min(start_index, len(start_stacks) - 1)),
            )
            if hand_state is None:
                return False, error or "Failed to start hand.", False

            table["round"] = int(table.get("round", 0)) + 1
            table["phase"] = POKER_LAN_PHASE_IN_HAND
            table["in_progress"] = True
            table["hand_state"] = hand_state
            table["turn_started_epoch"] = time.time()
            table["hand_start_stacks"] = {
                player["name"]: int(player.get("stack", 0)) + int(player.get("committed_total", 0))
                for player in hand_state.get("players", [])
            }
            table["dealer_index"] = (int(table.get("dealer_index", 0)) + 1) % max(1, len(seated_eligible))
            for name in table.get("players", []):
                table.setdefault("player_states", {}).setdefault(name, _normalize_poker_player_state({}))
                table["player_states"][name]["ready"] = _poker_is_bot_name(name)
            _poker_run_bot_actions_unlocked(table)
            if hand_state.get("street") == "finished":
                _poker_finalize_finished_hand_unlocked(data, table)
            _poker_lan_append_history(table, f"Round {table['round']} started.")
            data["poker_lan"] = lan_state
            _write_data_unlocked(data)
            return True, f"Round {table['round']} started.", True

        data["poker_lan"] = lan_state
        _write_data_unlocked(data)
        return True, "You are ready.", False


def poker_lan_player_action(table_id, player_name, action, amount=None):
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player."
    normalized_player = player_name.strip()
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_poker_lan_state(data.get("poker_lan", {}))
        table = _poker_lan_table_by_id(lan_state, table_id)
        if table is None:
            return False, "Table not found."
        if not bool(table.get("in_progress")):
            return False, "No active hand."
        hand_state = table.get("hand_state")
        if not isinstance(hand_state, dict):
            return False, "Hand state unavailable."

        legal = poker_legal_actions(hand_state, normalized_player)
        if not legal.get("actions"):
            return False, "You cannot act right now."

        ok, message = poker_apply_action(hand_state, normalized_player, action, amount)
        if not ok:
            return False, message

        table["hand_state"] = hand_state
        table["turn_started_epoch"] = time.time()
        _poker_lan_append_history(table, f"{normalized_player}: {str(action).lower()}")

        _poker_run_bot_actions_unlocked(table)
        hand_state = table.get("hand_state")
        if hand_state.get("street") == "finished":
            _poker_finalize_finished_hand_unlocked(data, table)

        data["poker_lan"] = lan_state
        _write_data_unlocked(data)
        return True, "Action submitted."
