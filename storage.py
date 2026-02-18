"""Persistent storage helpers for accounts and odds."""

import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from random import shuffle
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from money_utils import house_round_balance, house_round_credit, house_round_delta

DEFAULT_ODDS = 1.5
ACCOUNTS_FILE = "accounts.json"
ODDS_ACCOUNT_KEY = "__house_odds__"
GAME_STAT_KEYS = {"player_guess", "computer_guess", "blackjack"}
DEFAULT_ACCOUNT_SESSION_TTL_SECONDS = 6 * 60 * 60
BLACKJACK_LAN_ACTIVITY_TTL_SECONDS = 30
BLACKJACK_LAN_DEFAULT_TABLE_COUNT = 5
BLACKJACK_LAN_MIN_TABLE_PLAYERS = 1
BLACKJACK_LAN_MAX_TABLE_PLAYERS = 8
BLACKJACK_LAN_DEFAULT_MAX_PLAYERS_PER_TABLE = 5
BLACKJACK_LAN_DEFAULT_MIN_BET = 0.01
BLACKJACK_LAN_DEFAULT_MAX_BET = None
BLACKJACK_LAN_DEFAULT_TURN_TIMEOUT_SECONDS = 30
BLACKJACK_LAN_DEFAULT_TIMEOUT_PENALTY_PERCENT = 25.0
BLACKJACK_DEALER_STAND_TOTAL = 17
BLACKJACK_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
BLACKJACK_SUITS = ["S", "H", "D", "C"]
BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS = "waiting_for_players"
BLACKJACK_LAN_PHASE_WAITING_FOR_BETS = "waiting_for_bets"
BLACKJACK_LAN_PHASE_PLAYER_TURNS = "player_turns"
BLACKJACK_LAN_PHASE_FINISHED = "finished"

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows-only fallback
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX-only fallback
    msvcrt = None


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
        "blackjack_lan": _default_blackjack_lan_state(),
    }


def _default_blackjack_lan_player_state():
    return {
        "bet": 0.0,
        "ready": False,
        "cards": [],
        "status": "waiting",
        "result": None,
        "message": "",
        "payout": 0.0,
        "is_natural": False,
        "penalty_charged": 0.0,
    }


def _default_blackjack_lan_settings():
    return {
        "default_max_players": BLACKJACK_LAN_DEFAULT_MAX_PLAYERS_PER_TABLE,
        "default_min_bet": BLACKJACK_LAN_DEFAULT_MIN_BET,
        "default_max_bet": BLACKJACK_LAN_DEFAULT_MAX_BET,
        "allow_spectators_by_default": True,
        "turn_timeout_seconds": BLACKJACK_LAN_DEFAULT_TURN_TIMEOUT_SECONDS,
        "timeout_penalty_percent": BLACKJACK_LAN_DEFAULT_TIMEOUT_PENALTY_PERCENT,
    }


def _coerce_blackjack_lan_max_players(raw_value, fallback):
    try:
        normalized = int(raw_value)
    except (TypeError, ValueError):
        normalized = int(fallback)
    return max(BLACKJACK_LAN_MIN_TABLE_PLAYERS, min(BLACKJACK_LAN_MAX_TABLE_PLAYERS, normalized))


def _coerce_blackjack_lan_bet_amount(raw_value, fallback, *, allow_none=False):
    if allow_none and raw_value is None:
        return None
    try:
        normalized = house_round_credit(float(raw_value))
    except Exception:
        normalized = fallback
    try:
        normalized_value = house_round_credit(float(normalized))
    except Exception:
        normalized_value = fallback
    if normalized_value is None and allow_none:
        return None
    if normalized_value is None:
        normalized_value = BLACKJACK_LAN_DEFAULT_MIN_BET
    return max(0.0, float(normalized_value))


def _normalize_blackjack_lan_settings(raw_settings):
    settings = _default_blackjack_lan_settings()
    if not isinstance(raw_settings, dict):
        return settings
    settings["default_max_players"] = _coerce_blackjack_lan_max_players(
        raw_settings.get("default_max_players", settings["default_max_players"]),
        settings["default_max_players"],
    )
    settings["default_min_bet"] = _coerce_blackjack_lan_bet_amount(
        raw_settings.get("default_min_bet", settings["default_min_bet"]),
        settings["default_min_bet"],
    )
    settings["default_max_bet"] = _coerce_blackjack_lan_bet_amount(
        raw_settings.get("default_max_bet", settings["default_max_bet"]),
        settings["default_max_bet"],
        allow_none=True,
    )
    if settings["default_max_bet"] is not None and settings["default_max_bet"] < settings["default_min_bet"]:
        settings["default_max_bet"] = settings["default_min_bet"]
    settings["allow_spectators_by_default"] = bool(
        raw_settings.get("allow_spectators_by_default", settings["allow_spectators_by_default"])
    )
    try:
        timeout_seconds = int(raw_settings.get("turn_timeout_seconds", settings["turn_timeout_seconds"]))
    except (TypeError, ValueError):
        timeout_seconds = settings["turn_timeout_seconds"]
    settings["turn_timeout_seconds"] = max(5, timeout_seconds)
    try:
        penalty_percent = float(raw_settings.get("timeout_penalty_percent", settings["timeout_penalty_percent"]))
    except (TypeError, ValueError):
        penalty_percent = settings["timeout_penalty_percent"]
    settings["timeout_penalty_percent"] = max(0.0, min(100.0, penalty_percent))
    return settings


def _default_blackjack_lan_table(table_id, settings=None):
    normalized_settings = _normalize_blackjack_lan_settings(settings or {})
    max_players = int(normalized_settings["default_max_players"])
    min_bet = float(normalized_settings["default_min_bet"])
    max_bet = normalized_settings["default_max_bet"]
    return {
        "id": int(table_id),
        "name": _normalize_blackjack_lan_table_name(None, table_id),
        "players": [],
        "pending_players": [],
        "host": None,
        "max_players": max_players,
        "min_bet": min_bet,
        "max_bet": max_bet,
        "allow_spectators": bool(normalized_settings.get("allow_spectators_by_default", True)),
        "spectators_require_password": False,
        "is_private": False,
        "password": "",
        "phase": BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS,
        "round": 0,
        "in_progress": False,
        "dealer_cards": [],
        "deck": [],
        "turn_order": [],
        "turn_index": 0,
        "turn_started_epoch": 0.0,
        "player_states": {},
        "history": [],
        "last_updated_epoch": 0.0,
    }


def _default_blackjack_lan_state():
    settings = _default_blackjack_lan_settings()
    return {
        "settings": settings,
        "tables": [_default_blackjack_lan_table(index + 1, settings=settings) for index in range(BLACKJACK_LAN_DEFAULT_TABLE_COUNT)],
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


def _blackjack_new_deck():
    deck = [(rank, suit) for suit in BLACKJACK_SUITS for rank in BLACKJACK_RANKS]
    shuffle(deck)
    return deck


def _blackjack_draw_card_from_table(table):
    if not isinstance(table.get("deck"), list) or not table["deck"]:
        table["deck"] = _blackjack_new_deck()
    return table["deck"].pop()


def _blackjack_hand_total(cards):
    total = 0
    aces = 0
    for card in cards:
        if not isinstance(card, (list, tuple)) or len(card) < 1:
            continue
        rank = str(card[0])
        if rank == "A":
            total += 11
            aces += 1
        elif rank in {"J", "Q", "K"}:
            total += 10
        else:
            try:
                total += int(rank)
            except (TypeError, ValueError):
                total += 0
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def _blackjack_is_natural(cards):
    return len(cards) == 2 and _blackjack_hand_total(cards) == 21


def _coerce_blackjack_table_id(table_id):
    try:
        normalized = int(table_id)
    except (TypeError, ValueError):
        return None
    if normalized < 1:
        return None
    return normalized


def _normalize_blackjack_lan_table_name(raw_value, fallback_id):
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
    else:
        normalized = ""
    if not normalized:
        normalized = f"Table {int(fallback_id)}"
    if len(normalized) > 60:
        normalized = normalized[:60].strip()
    return normalized


def _blackjack_lan_table_name_key(name):
    if not isinstance(name, str):
        return ""
    return name.strip().casefold()


def _normalize_blackjack_lan_table(raw_table, fallback_id, settings=None):
    normalized_settings = _normalize_blackjack_lan_settings(settings or {})
    table = _default_blackjack_lan_table(fallback_id, settings=normalized_settings)
    if not isinstance(raw_table, dict):
        return table

    normalized_id = _coerce_blackjack_table_id(raw_table.get("id"))
    if normalized_id is None:
        normalized_id = _coerce_blackjack_table_id(fallback_id)
    if normalized_id is None:
        normalized_id = int(fallback_id)
    table["id"] = normalized_id
    table["name"] = _normalize_blackjack_lan_table_name(
        raw_table.get("name", f"Table {normalized_id}"),
        normalized_id,
    )

    table["max_players"] = _coerce_blackjack_lan_max_players(
        raw_table.get("max_players", table["max_players"]),
        table["max_players"],
    )
    table["min_bet"] = _coerce_blackjack_lan_bet_amount(
        raw_table.get("min_bet", table["min_bet"]),
        table["min_bet"],
    )
    table["max_bet"] = _coerce_blackjack_lan_bet_amount(
        raw_table.get("max_bet", table["max_bet"]),
        table["max_bet"],
        allow_none=True,
    )
    if table["max_bet"] is not None and table["max_bet"] < table["min_bet"]:
        table["max_bet"] = table["min_bet"]

    raw_players = raw_table.get("players", [])
    players = []
    if isinstance(raw_players, list):
        for raw_player in raw_players:
            if not isinstance(raw_player, str):
                continue
            player = raw_player.strip()
            if not player or player in players:
                continue
            players.append(player)
            if len(players) >= int(table["max_players"]):
                break
    table["players"] = players

    raw_pending_players = raw_table.get("pending_players", [])
    pending_players = []
    if isinstance(raw_pending_players, list):
        for raw_player in raw_pending_players:
            if not isinstance(raw_player, str):
                continue
            player = raw_player.strip()
            if not player:
                continue
            if player in players or player in pending_players:
                continue
            pending_players.append(player)
            if len(players) + len(pending_players) >= int(table["max_players"]):
                break
    table["pending_players"] = pending_players

    host = raw_table.get("host")
    if isinstance(host, str) and host in players:
        table["host"] = host
    elif players:
        table["host"] = players[0]

    table["allow_spectators"] = bool(raw_table.get("allow_spectators", table["allow_spectators"]))
    table["spectators_require_password"] = bool(
        raw_table.get("spectators_require_password", table["spectators_require_password"])
    )
    table["is_private"] = bool(raw_table.get("is_private", False))
    raw_password = raw_table.get("password", "")
    table["password"] = str(raw_password) if raw_password is not None else ""

    raw_phase = raw_table.get("phase")
    valid_phases = {
        BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS,
        BLACKJACK_LAN_PHASE_WAITING_FOR_BETS,
        BLACKJACK_LAN_PHASE_PLAYER_TURNS,
        BLACKJACK_LAN_PHASE_FINISHED,
    }
    if isinstance(raw_phase, str) and raw_phase in valid_phases:
        table["phase"] = raw_phase
    elif players:
        table["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_BETS

    try:
        table["round"] = max(0, int(raw_table.get("round", 0)))
    except (TypeError, ValueError):
        table["round"] = 0
    table["in_progress"] = bool(raw_table.get("in_progress", False))

    raw_dealer_cards = raw_table.get("dealer_cards", [])
    if isinstance(raw_dealer_cards, list):
        table["dealer_cards"] = [card for card in raw_dealer_cards if isinstance(card, (list, tuple)) and len(card) == 2]

    raw_deck = raw_table.get("deck", [])
    if isinstance(raw_deck, list):
        table["deck"] = [card for card in raw_deck if isinstance(card, (list, tuple)) and len(card) == 2]

    raw_turn_order = raw_table.get("turn_order", [])
    if isinstance(raw_turn_order, list):
        turn_order = []
        for raw_player in raw_turn_order:
            if raw_player in players and raw_player not in turn_order:
                turn_order.append(raw_player)
        table["turn_order"] = turn_order

    try:
        table["turn_index"] = max(0, int(raw_table.get("turn_index", 0)))
    except (TypeError, ValueError):
        table["turn_index"] = 0
    try:
        table["turn_started_epoch"] = float(raw_table.get("turn_started_epoch", 0.0))
    except (TypeError, ValueError):
        table["turn_started_epoch"] = 0.0

    raw_history = raw_table.get("history", [])
    if isinstance(raw_history, list):
        table["history"] = [str(item) for item in raw_history if isinstance(item, str)]

    try:
        table["last_updated_epoch"] = float(raw_table.get("last_updated_epoch", 0.0))
    except (TypeError, ValueError):
        table["last_updated_epoch"] = 0.0

    raw_player_states = raw_table.get("player_states", {})
    normalized_player_states = {}
    if isinstance(raw_player_states, dict):
        for player_name in players:
            raw_player_state = raw_player_states.get(player_name, {})
            state = _default_blackjack_lan_player_state()
            if isinstance(raw_player_state, dict):
                try:
                    state["bet"] = house_round_credit(float(raw_player_state.get("bet", 0.0)))
                except Exception:
                    state["bet"] = 0.0
                state["ready"] = bool(raw_player_state.get("ready", False))
                raw_cards = raw_player_state.get("cards", [])
                if isinstance(raw_cards, list):
                    state["cards"] = [
                        card for card in raw_cards if isinstance(card, (list, tuple)) and len(card) == 2
                    ]
                raw_status = raw_player_state.get("status")
                if isinstance(raw_status, str):
                    state["status"] = raw_status
                raw_result = raw_player_state.get("result")
                if raw_result is None or isinstance(raw_result, str):
                    state["result"] = raw_result
                raw_message = raw_player_state.get("message")
                if isinstance(raw_message, str):
                    state["message"] = raw_message
                try:
                    state["payout"] = house_round_credit(float(raw_player_state.get("payout", 0.0)))
                except Exception:
                    state["payout"] = 0.0
                state["is_natural"] = bool(raw_player_state.get("is_natural", False))
                try:
                    state["penalty_charged"] = house_round_credit(
                        float(raw_player_state.get("penalty_charged", 0.0))
                    )
                except Exception:
                    state["penalty_charged"] = 0.0
            normalized_player_states[player_name] = state
    else:
        for player_name in players:
            normalized_player_states[player_name] = _default_blackjack_lan_player_state()
    table["player_states"] = normalized_player_states

    if table["phase"] == BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS and players:
        table["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_BETS
    if not players:
        table["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS
        table["in_progress"] = False
        table["turn_order"] = []
        table["turn_index"] = 0
        table["turn_started_epoch"] = 0.0
        # Keep pending players queued for the next hand if table already exists.

    return table


def _normalize_blackjack_lan_state(raw_state):
    state = _default_blackjack_lan_state()
    if not isinstance(raw_state, dict):
        return state
    settings = _normalize_blackjack_lan_settings(raw_state.get("settings", {}))
    state["settings"] = settings
    raw_tables = raw_state.get("tables", None)
    normalized_by_id = {}
    if isinstance(raw_tables, list):
        for index, raw_table in enumerate(raw_tables):
            fallback_id = index + 1
            normalized = _normalize_blackjack_lan_table(raw_table, fallback_id, settings=settings)
            table_id = int(normalized["id"])
            if table_id in normalized_by_id:
                continue
            normalized_by_id[table_id] = normalized
    tables = sorted(normalized_by_id.values(), key=lambda item: int(item.get("id", 0)))
    if (raw_tables is None) and (not tables):
        tables = [
            _default_blackjack_lan_table(index + 1, settings=settings)
            for index in range(BLACKJACK_LAN_DEFAULT_TABLE_COUNT)
        ]
    state["tables"] = tables
    return state


def _blackjack_lan_table_by_id(lan_state, table_id):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return None
    for table in lan_state.get("tables", []):
        if int(table.get("id", -1)) == normalized_id:
            return table
    return None


def _blackjack_lan_table_member_state(table, player_name):
    normalized = str(player_name).strip()
    if not normalized:
        return None
    if normalized in table.get("players", []):
        return "seated"
    if normalized in table.get("pending_players", []):
        return "pending"
    return None


def _blackjack_lan_promote_pending_players_unlocked(data, table):
    if bool(table.get("in_progress")):
        return
    players = list(table.get("players", []))
    pending_players = list(table.get("pending_players", []))
    if not pending_players:
        return
    max_players = int(table.get("max_players", BLACKJACK_LAN_DEFAULT_MAX_PLAYERS_PER_TABLE))
    promoted = []
    remaining = []
    for player_name in pending_players:
        if player_name in players:
            continue
        if len(players) >= max_players:
            remaining.append(player_name)
            continue
        if player_name not in data.get("accounts", {}):
            continue
        players.append(player_name)
        table.setdefault("player_states", {})[player_name] = _default_blackjack_lan_player_state()
        promoted.append(player_name)
    table["players"] = players
    table["pending_players"] = remaining
    if promoted:
        table["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_BETS
        table["last_updated_epoch"] = time.time()
        for player_name in promoted:
            _blackjack_lan_append_history(table, f"{player_name} joined from queue for the next hand.")


def _blackjack_lan_current_turn_player(table):
    turn_order = table.get("turn_order", [])
    turn_index = int(table.get("turn_index", 0))
    if not isinstance(turn_order, list) or turn_index < 0 or turn_index >= len(turn_order):
        return None
    current_player = turn_order[turn_index]
    if not isinstance(current_player, str):
        return None
    return current_player


def _blackjack_lan_next_table_id(lan_state):
    max_id = 0
    for table in lan_state.get("tables", []):
        try:
            table_id = int(table.get("id", 0))
        except (TypeError, ValueError):
            table_id = 0
        if table_id > max_id:
            max_id = table_id
    return max_id + 1


def _blackjack_lan_normalize_table_bet_limits(table):
    min_bet = _coerce_blackjack_lan_bet_amount(table.get("min_bet", BLACKJACK_LAN_DEFAULT_MIN_BET), BLACKJACK_LAN_DEFAULT_MIN_BET)
    max_bet = _coerce_blackjack_lan_bet_amount(table.get("max_bet", BLACKJACK_LAN_DEFAULT_MAX_BET), BLACKJACK_LAN_DEFAULT_MAX_BET, allow_none=True)
    if max_bet is not None and max_bet < min_bet:
        max_bet = min_bet
    table["min_bet"] = min_bet
    table["max_bet"] = max_bet


def _blackjack_lan_is_bet_allowed(table, bet):
    _blackjack_lan_normalize_table_bet_limits(table)
    amount = house_round_credit(bet)
    min_bet = float(table.get("min_bet", BLACKJACK_LAN_DEFAULT_MIN_BET))
    max_bet = table.get("max_bet")
    if amount < min_bet:
        return False, f"Minimum table bet is ${min_bet:.2f}."
    if max_bet is not None and amount > float(max_bet):
        return False, f"Maximum table bet is ${float(max_bet):.2f}."
    return True, ""


def _blackjack_lan_ready_counts(table):
    players = list(table.get("players", []))
    ready_count = 0
    for player_name in players:
        player_state = table.get("player_states", {}).get(player_name, {})
        if bool(player_state.get("ready", False)):
            ready_count += 1
    return ready_count, len(players)


def _blackjack_lan_record_result_unlocked(data, name, buy_in, payout, won):
    account = data.get("accounts", {}).get(name)
    if not isinstance(account, dict):
        return False
    stats = _normalize_account_stats(account.get("stats", {}))
    _apply_result_to_stats_bucket(stats, buy_in, payout, won)
    breakdown = stats.get("game_breakdown", {})
    game_stats = _normalize_stats_bucket(breakdown.get("blackjack", {}))
    _apply_result_to_stats_bucket(game_stats, buy_in, payout, won)
    breakdown["blackjack"] = game_stats
    stats["game_breakdown"] = breakdown
    account["stats"] = stats
    return True


def _blackjack_lan_append_history(table, message):
    if not isinstance(message, str) or not message.strip():
        return
    history = table.setdefault("history", [])
    history.append(message.strip())
    if len(history) > 80:
        del history[:-80]


def _blackjack_lan_advance_turn_unlocked(table):
    table["turn_index"] = int(table.get("turn_index", 0)) + 1
    table["turn_started_epoch"] = time.time()
    turn_order = table.get("turn_order", [])
    if int(table["turn_index"]) >= len(turn_order):
        table["turn_started_epoch"] = 0.0
        return None
    return _blackjack_lan_current_turn_player(table)


def _blackjack_lan_eject_player_for_timeout_unlocked(data, table, player_name, settings):
    players = table.get("players", [])
    if player_name not in players:
        return
    player_state = table.get("player_states", {}).get(player_name, _default_blackjack_lan_player_state())
    bet = house_round_credit(player_state.get("bet", 0.0))
    penalty_percent = float(settings.get("timeout_penalty_percent", BLACKJACK_LAN_DEFAULT_TIMEOUT_PENALTY_PERCENT))
    penalty = house_round_credit((bet * penalty_percent) / 100.0)
    account = data.get("accounts", {}).get(player_name)
    if isinstance(account, dict) and penalty > 0:
        account["balance"] = house_round_balance(account.get("balance", 0.0) - penalty)
    _blackjack_lan_record_result_unlocked(data, player_name, bet + penalty, 0.0, False)
    player_state["penalty_charged"] = penalty
    player_state["status"] = "timed_out"
    player_state["result"] = "loss"
    player_state["payout"] = 0.0
    player_state["message"] = (
        f"Timed out and ejected. Penalty charged: ${penalty:.2f}."
    )
    table["players"] = [p for p in players if p != player_name]
    table.get("player_states", {}).pop(player_name, None)
    table["turn_order"] = [p for p in table.get("turn_order", []) if p != player_name]
    if table.get("host") == player_name:
        table["host"] = table["players"][0] if table["players"] else None
    if not table["players"]:
        reset_table = _default_blackjack_lan_table(table.get("id", 1), settings=settings)
        reset_table["name"] = _normalize_blackjack_lan_table_name(
            table.get("name", reset_table.get("name", "")),
            table.get("id", 1),
        )
        table.clear()
        table.update(reset_table)
        return
    _blackjack_lan_append_history(
        table,
        f"{player_name} timed out, was ejected, and penalized ${penalty:.2f}.",
    )


def _blackjack_lan_enforce_timeout_for_table_unlocked(data, table, settings):
    if table.get("phase") != BLACKJACK_LAN_PHASE_PLAYER_TURNS or not bool(table.get("in_progress")):
        return
    timeout_seconds = int(settings.get("turn_timeout_seconds", BLACKJACK_LAN_DEFAULT_TURN_TIMEOUT_SECONDS))
    timeout_seconds = max(5, timeout_seconds)
    turn_started_epoch = float(table.get("turn_started_epoch", 0.0) or 0.0)
    if turn_started_epoch <= 0:
        table["turn_started_epoch"] = time.time()
        return
    now_epoch = time.time()
    if now_epoch - turn_started_epoch < timeout_seconds:
        return
    timed_out_player = _blackjack_lan_current_turn_player(table)
    if timed_out_player is None:
        return
    _blackjack_lan_eject_player_for_timeout_unlocked(data, table, timed_out_player, settings)
    if table.get("phase") != BLACKJACK_LAN_PHASE_PLAYER_TURNS:
        return
    current_turn = _blackjack_lan_current_turn_player(table)
    if current_turn is None:
        _blackjack_lan_append_history(table, "Dealer turn.")
        _blackjack_lan_finish_round_unlocked(data, table)
    else:
        table["turn_started_epoch"] = time.time()
        table["last_updated_epoch"] = now_epoch


def _blackjack_lan_is_account_active_unlocked(data, account_name, now_epoch, ttl_seconds):
    sessions = _normalize_active_sessions(
        data.get("active_sessions", {}),
        set(data.get("accounts", {}).keys()),
    )
    entry = sessions.get(account_name)
    if not isinstance(entry, dict):
        return False
    try:
        last_seen = float(entry.get("last_seen_epoch", 0.0))
    except (TypeError, ValueError):
        return False
    if last_seen <= 0:
        return False
    return (now_epoch - last_seen) <= ttl_seconds


def _blackjack_lan_eject_player_for_disconnect_unlocked(data, table, player_name, settings):
    players = table.get("players", [])
    if player_name not in players:
        return

    player_state = table.get("player_states", {}).get(player_name, _default_blackjack_lan_player_state())
    bet = house_round_credit(player_state.get("bet", 0.0))
    if bet > 0:
        _blackjack_lan_record_result_unlocked(data, player_name, bet, 0.0, False)

    old_turn_order = list(table.get("turn_order", []))
    old_turn_index = int(table.get("turn_index", 0))
    removed_turn_position = -1
    if player_name in old_turn_order:
        removed_turn_position = old_turn_order.index(player_name)

    table["players"] = [player for player in players if player != player_name]
    table.get("player_states", {}).pop(player_name, None)
    table["turn_order"] = [player for player in old_turn_order if player != player_name]

    if removed_turn_position >= 0 and removed_turn_position < old_turn_index:
        table["turn_index"] = max(0, old_turn_index - 1)
    else:
        table["turn_index"] = max(0, old_turn_index)

    if table.get("host") == player_name:
        table["host"] = table["players"][0] if table["players"] else None

    _blackjack_lan_append_history(
        table,
        f"{player_name} disconnected unexpectedly and was removed from the hand.",
    )

    if not table["players"]:
        reset_table = _default_blackjack_lan_table(table.get("id", 1), settings=settings)
        reset_table["name"] = _normalize_blackjack_lan_table_name(
            table.get("name", reset_table.get("name", "")),
            table.get("id", 1),
        )
        table.clear()
        table.update(reset_table)
        return

    table["last_updated_epoch"] = time.time()


def _blackjack_lan_remove_player_after_disconnect_unlocked(table, player_name, settings):
    membership = _blackjack_lan_table_member_state(table, player_name)
    if membership is None:
        return

    if membership == "pending":
        table["pending_players"] = [
            player for player in table.get("pending_players", []) if player != player_name
        ]
        _blackjack_lan_append_history(
            table,
            f"{player_name} disconnected and was removed from the join queue.",
        )
        table["last_updated_epoch"] = time.time()
        return

    players = list(table.get("players", []))
    if player_name not in players:
        return

    old_turn_order = list(table.get("turn_order", []))
    old_turn_index = int(table.get("turn_index", 0))
    removed_turn_position = -1
    if player_name in old_turn_order:
        removed_turn_position = old_turn_order.index(player_name)

    table["players"] = [player for player in players if player != player_name]
    table.get("player_states", {}).pop(player_name, None)
    table["turn_order"] = [player for player in old_turn_order if player != player_name]
    if removed_turn_position >= 0 and removed_turn_position < old_turn_index:
        table["turn_index"] = max(0, old_turn_index - 1)
    else:
        table["turn_index"] = max(0, old_turn_index)

    if table.get("host") == player_name:
        table["host"] = table["players"][0] if table["players"] else None

    _blackjack_lan_append_history(
        table,
        f"{player_name} disconnected and was removed from the table.",
    )

    if not table["players"]:
        reset_table = _default_blackjack_lan_table(table.get("id", 1), settings=settings)
        reset_table["name"] = _normalize_blackjack_lan_table_name(
            table.get("name", reset_table.get("name", "")),
            table.get("id", 1),
        )
        table.clear()
        table.update(reset_table)
        return

    table["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_BETS
    table["in_progress"] = False
    table["turn_order"] = []
    table["turn_index"] = 0
    table["turn_started_epoch"] = 0.0
    table["dealer_cards"] = []
    table["deck"] = []
    table["last_updated_epoch"] = time.time()


def _blackjack_lan_handle_unexpected_disconnects_unlocked(data, lan_state, settings):
    now_epoch = time.time()
    ttl_seconds = _coerce_session_ttl_seconds(BLACKJACK_LAN_ACTIVITY_TTL_SECONDS)
    _prune_expired_sessions_unlocked(data, now_epoch, ttl_seconds)

    for table in lan_state.get("tables", []):
        table_players = list(table.get("players", []))
        table_pending_players = list(table.get("pending_players", []))
        disconnected_players = [
            player
            for player in (table_players + [p for p in table_pending_players if p not in table_players])
            if not _blackjack_lan_is_account_active_unlocked(data, player, now_epoch, ttl_seconds)
        ]
        if not disconnected_players:
            continue

        for player_name in disconnected_players:
            if (
                player_name in table.get("players", [])
                and table.get("phase") == BLACKJACK_LAN_PHASE_PLAYER_TURNS
                and bool(table.get("in_progress"))
            ):
                _blackjack_lan_eject_player_for_disconnect_unlocked(data, table, player_name, settings)
            else:
                _blackjack_lan_remove_player_after_disconnect_unlocked(table, player_name, settings)

        if table.get("phase") != BLACKJACK_LAN_PHASE_PLAYER_TURNS:
            continue
        if not bool(table.get("in_progress")):
            continue

        current_turn = _blackjack_lan_current_turn_player(table)
        if current_turn is None:
            _blackjack_lan_append_history(table, "Dealer turn.")
            _blackjack_lan_finish_round_unlocked(data, table)
        else:
            table["turn_started_epoch"] = time.time()
            table["last_updated_epoch"] = time.time()


def _blackjack_lan_force_remove_player_unlocked(data, lan_state, player_name):
    settings = _normalize_blackjack_lan_settings(lan_state.get("settings", {}))
    removed = False
    for table in lan_state.get("tables", []):
        membership = _blackjack_lan_table_member_state(table, player_name)
        if membership is None:
            continue
        removed = True
        if (
            membership == "seated"
            and table.get("phase") == BLACKJACK_LAN_PHASE_PLAYER_TURNS
            and bool(table.get("in_progress"))
        ):
            _blackjack_lan_eject_player_for_disconnect_unlocked(data, table, player_name, settings)
            if table.get("phase") == BLACKJACK_LAN_PHASE_PLAYER_TURNS and bool(table.get("in_progress")):
                current_turn = _blackjack_lan_current_turn_player(table)
                if current_turn is None:
                    _blackjack_lan_append_history(table, "Dealer turn.")
                    _blackjack_lan_finish_round_unlocked(data, table)
                else:
                    table["turn_started_epoch"] = time.time()
                    table["last_updated_epoch"] = time.time()
        else:
            _blackjack_lan_remove_player_after_disconnect_unlocked(table, player_name, settings)
    return removed


def _blackjack_lan_enforce_timeouts_unlocked(data, lan_state):
    settings = _normalize_blackjack_lan_settings(lan_state.get("settings", {}))
    _blackjack_lan_handle_unexpected_disconnects_unlocked(data, lan_state, settings)
    for table in lan_state.get("tables", []):
        _blackjack_lan_promote_pending_players_unlocked(data, table)
        _blackjack_lan_enforce_timeout_for_table_unlocked(data, table, settings)


def _persist_if_changed_unlocked(data, before_data):
    if data != before_data:
        _write_data_unlocked(data)


def _blackjack_lan_finish_round_unlocked(data, table):
    while _blackjack_hand_total(table.get("dealer_cards", [])) < BLACKJACK_DEALER_STAND_TOTAL:
        table["dealer_cards"].append(_blackjack_draw_card_from_table(table))

    dealer_cards = table.get("dealer_cards", [])
    dealer_total = _blackjack_hand_total(dealer_cards)
    dealer_natural = _blackjack_is_natural(dealer_cards)

    for player_name in list(table.get("players", [])):
        player_state = table.get("player_states", {}).get(player_name)
        if not isinstance(player_state, dict):
            continue
        bet = house_round_credit(player_state.get("bet", 0.0))
        if bet <= 0:
            continue

        player_cards = player_state.get("cards", [])
        player_total = _blackjack_hand_total(player_cards)
        player_natural = bool(player_state.get("is_natural", False))
        status = str(player_state.get("status", "waiting"))

        result = "loss"
        payout = 0.0
        won = False
        message = "You lose this round."

        if status == "busted" or player_total > 21:
            result = "loss"
            message = f"Busted with {player_total}. You lose."
        elif dealer_total > 21:
            if player_natural and not dealer_natural:
                result = "blackjack"
                payout = house_round_credit(bet * 2.5)
                won = True
                message = f"Dealer busted with {dealer_total}. Blackjack payout 3:2."
            else:
                result = "win"
                payout = house_round_credit(bet * 2.0)
                won = True
                message = f"Dealer busted with {dealer_total}. You win."
        elif player_natural and not dealer_natural:
            result = "blackjack"
            payout = house_round_credit(bet * 2.5)
            won = True
            message = "Blackjack! You win 3:2."
        elif dealer_natural and not player_natural:
            result = "loss"
            message = "Dealer blackjack. You lose."
        elif player_total > dealer_total:
            result = "win"
            payout = house_round_credit(bet * 2.0)
            won = True
            message = f"Your {player_total} beats dealer {dealer_total}."
        elif player_total == dealer_total:
            result = "push"
            payout = house_round_credit(bet)
            message = f"Push at {player_total}. Bet returned."
        else:
            result = "loss"
            message = f"Dealer {dealer_total} beats your {player_total}."

        account = data.get("accounts", {}).get(player_name)
        if isinstance(account, dict):
            if payout > 0:
                account["balance"] = house_round_balance(account.get("balance", 0.0) + payout)
            _blackjack_lan_record_result_unlocked(data, player_name, bet, payout, won)

        player_state["payout"] = payout
        player_state["result"] = result
        player_state["message"] = message
        player_state["status"] = "finished"

    table["phase"] = BLACKJACK_LAN_PHASE_FINISHED
    table["in_progress"] = False
    table["turn_order"] = []
    table["turn_index"] = 0
    table["turn_started_epoch"] = 0.0
    table["last_updated_epoch"] = time.time()
    _blackjack_lan_append_history(table, f"Dealer final total: {dealer_total}. Round finished.")


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
        _storage_backend_cache = {"type": "local"}
    return _storage_backend_cache


def _invalidate_state_read_cache():
    global _state_read_cache
    _state_read_cache = None


def _get_local_accounts_mtime_unlocked():
    try:
        return os.path.getmtime(ACCOUNTS_FILE)
    except FileNotFoundError:
        return None


def _is_cached_state_valid_unlocked(backend):
    if not isinstance(_state_read_cache, dict):
        return False
    cached_backend_type = _state_read_cache.get("backend_type")
    backend_type = backend.get("type")
    if cached_backend_type != backend_type:
        return False
    if backend_type == "local":
        return _state_read_cache.get("local_mtime") == _get_local_accounts_mtime_unlocked()
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
        "local_mtime": _get_local_accounts_mtime_unlocked() if backend_type == "local" else None,
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


def _read_local_data_unlocked():
    with open(ACCOUNTS_FILE, "r") as file:
        loaded = json.load(file)
    if not isinstance(loaded, dict):
        raise ValueError("JSON root must be an object.")
    return loaded


def _lock_file(lock_file):
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        return
    if msvcrt is not None:  # pragma: no cover - Windows-only fallback
        lock_file.seek(0, os.SEEK_SET)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        return
    raise RuntimeError("No file locking mechanism available on this platform.")


def _unlock_file(lock_file):
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return
    if msvcrt is not None:  # pragma: no cover - Windows-only fallback
        lock_file.seek(0, os.SEEK_SET)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return
    raise RuntimeError("No file locking mechanism available on this platform.")


@contextmanager
def _accounts_write_lock():
    backend = _get_storage_backend()
    if backend.get("type") == "supabase":
        with _in_process_write_lock:
            yield
        return

    lock_path = f"{ACCOUNTS_FILE}.lock"
    lock_dir = os.path.dirname(os.path.abspath(lock_path))
    os.makedirs(lock_dir, exist_ok=True)

    with open(lock_path, "a+") as lock_file:
        if msvcrt is not None and fcntl is None:  # pragma: no cover - Windows-only fallback
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write("0")
                lock_file.flush()
        _lock_file(lock_file)
        try:
            yield
        finally:
            _unlock_file(lock_file)


def _write_data_unlocked(data):
    backend = _get_storage_backend()
    if backend.get("type") == "supabase":
        _write_supabase_state_unlocked(data)
        _invalidate_state_read_cache()
        return

    destination = os.path.abspath(ACCOUNTS_FILE)
    destination_dir = os.path.dirname(destination) or "."
    os.makedirs(destination_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".accounts-", suffix=".tmp", dir=destination_dir)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(data, file, indent=2, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, destination)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
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

    data["blackjack_lan"] = _normalize_blackjack_lan_state(loaded.get("blackjack_lan", {}))
    return data


def _load_data_unlocked(use_cache=True):
    backend = _get_storage_backend()
    if use_cache and _is_cached_state_valid_unlocked(backend):
        # Return the cached normalized state directly to avoid repeatedly
        # deep-copying the full app state on every read helper call.
        return _state_read_cache.get("data")
    try:
        if backend.get("type") == "supabase":
            loaded = _read_supabase_state_unlocked()
            if loaded is None:
                _set_state_read_cache_unlocked(backend, None)
                return None
            normalized = _normalize_loaded_data(loaded)
            _set_state_read_cache_unlocked(backend, normalized)
            return normalized
        else:
            loaded = _read_local_data_unlocked()
        normalized = _normalize_loaded_data(loaded)
        _set_state_read_cache_unlocked(backend, normalized)
        return normalized
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
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
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        for table in lan_state.get("tables", []):
            table["pending_players"] = [player for player in table.get("pending_players", []) if player != name]
            players = [player for player in table.get("players", []) if player != name]
            if len(players) != len(table.get("players", [])):
                table["players"] = players
                table.get("player_states", {}).pop(name, None)
                if table.get("host") == name:
                    table["host"] = players[0] if players else None
                if not players:
                    reset_table = _default_blackjack_lan_table(
                        table.get("id", 1),
                        settings=lan_state.get("settings", {}),
                    )
                    reset_table["name"] = _normalize_blackjack_lan_table_name(
                        table.get("name", reset_table.get("name", "")),
                        table.get("id", 1),
                    )
                    table.clear()
                    table.update(reset_table)
                else:
                    if table.get("phase") == BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS:
                        table["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_BETS
                    table["last_updated_epoch"] = time.time()
        data["blackjack_lan"] = lan_state
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


def get_blackjack_lan_tables():
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        before_data = deepcopy(data)
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        data["blackjack_lan"] = lan_state
        _persist_if_changed_unlocked(data, before_data)
        return deepcopy(lan_state.get("tables", []))


def get_blackjack_lan_settings():
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        before_data = deepcopy(data)
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        data["blackjack_lan"] = lan_state
        _persist_if_changed_unlocked(data, before_data)
        return deepcopy(lan_state.get("settings", _default_blackjack_lan_settings()))


def get_blackjack_lan_table(table_id):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return None
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        before_data = deepcopy(data)
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        table = _blackjack_lan_table_by_id(lan_state, normalized_id)
        data["blackjack_lan"] = lan_state
        _persist_if_changed_unlocked(data, before_data)
        if table is None:
            return None
        return deepcopy(table)


def can_spectate_blackjack_lan_table(table_id, password=""):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return False, "Invalid table."
    provided_password = ""
    if password is not None:
        provided_password = str(password)
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        before_data = deepcopy(data)
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        table = _blackjack_lan_table_by_id(lan_state, normalized_id)
        if table is None:
            return False, "Table not found."
        settings = _normalize_blackjack_lan_settings(lan_state.get("settings", {}))
        if not bool(settings.get("allow_spectators_by_default", True)):
            return False, "Spectating is disabled by admin settings."
        if not bool(table.get("allow_spectators", True)):
            return False, "Spectating is disabled for this table."
        requires_password = bool(table.get("is_private", False)) or bool(
            table.get("spectators_require_password", False)
        )
        if requires_password:
            expected_password = str(table.get("password", ""))
            if not expected_password:
                return False, "Spectator password is not configured for this table."
            if expected_password and provided_password != expected_password:
                return False, "Incorrect table password."
        data["blackjack_lan"] = lan_state
        _persist_if_changed_unlocked(data, before_data)
        return True, "Spectating allowed."


def find_blackjack_lan_table_for_player(player_name):
    if not isinstance(player_name, str):
        return None
    normalized_player = player_name.strip()
    if not normalized_player:
        return None
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        before_data = deepcopy(data)
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        found = None
        for table in lan_state.get("tables", []):
            membership = _blackjack_lan_table_member_state(table, normalized_player)
            if membership is not None:
                found = deepcopy(table)
                found["membership"] = membership
                break
        data["blackjack_lan"] = lan_state
        _persist_if_changed_unlocked(data, before_data)
        return found


def create_blackjack_lan_table(
    max_players=None,
    min_bet=None,
    max_bet=None,
    allow_spectators=None,
    spectators_require_password=None,
    is_private=None,
    password=None,
    table_name=None,
):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        settings = _normalize_blackjack_lan_settings(lan_state.get("settings", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)

        table_id = _blackjack_lan_next_table_id(lan_state)
        table = _default_blackjack_lan_table(table_id, settings=settings)
        if max_players is not None:
            table["max_players"] = _coerce_blackjack_lan_max_players(max_players, table["max_players"])
        if min_bet is not None:
            table["min_bet"] = _coerce_blackjack_lan_bet_amount(min_bet, table["min_bet"])
        if max_bet is not None:
            table["max_bet"] = _coerce_blackjack_lan_bet_amount(max_bet, table["max_bet"], allow_none=True)
        if allow_spectators is not None:
            table["allow_spectators"] = bool(allow_spectators)
        if spectators_require_password is not None:
            table["spectators_require_password"] = bool(spectators_require_password)
        if is_private is not None:
            table["is_private"] = bool(is_private)
        if password is not None:
            table["password"] = str(password)
        if table_name is not None:
            table["name"] = _normalize_blackjack_lan_table_name(table_name, table_id)
        new_name_key = _blackjack_lan_table_name_key(table.get("name", ""))
        for existing in lan_state.get("tables", []):
            if _blackjack_lan_table_name_key(existing.get("name", "")) == new_name_key:
                return False, "A table with that name already exists."
        if bool(table.get("is_private", False)) and (not str(table.get("password", "")).strip()):
            return False, "Private tables must have a password."
        if bool(table.get("spectators_require_password", False)) and (not str(table.get("password", "")).strip()):
            return False, "Tables that require spectator passwords must have a password."
        if not bool(table.get("is_private", False)):
            if not bool(table.get("spectators_require_password", False)):
                table["password"] = ""
        _blackjack_lan_normalize_table_bet_limits(table)
        lan_state.setdefault("tables", []).append(table)
        lan_state["tables"] = sorted(lan_state.get("tables", []), key=lambda item: int(item.get("id", 0)))

        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        return True, f"Created table {table_id}."


def delete_blackjack_lan_table(table_id):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return False, "Invalid table."
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        tables = lan_state.get("tables", [])
        target = _blackjack_lan_table_by_id(lan_state, normalized_id)
        if target is None:
            return False, "Table not found."
        if bool(target.get("in_progress")):
            return False, "Cannot delete a table during an active hand."
        if target.get("players") or target.get("pending_players"):
            return False, "Cannot delete a table while players are still in or queued for it."
        lan_state["tables"] = [table for table in tables if int(table.get("id", -1)) != normalized_id]
        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        return True, f"Deleted table {normalized_id}."


def update_blackjack_lan_table_settings(
    table_id,
    max_players,
    min_bet,
    max_bet,
    allow_spectators=None,
    spectators_require_password=None,
    is_private=None,
    password=None,
    table_name=None,
):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return False, "Invalid table."
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        table = _blackjack_lan_table_by_id(lan_state, normalized_id)
        if table is None:
            return False, "Table not found."
        if bool(table.get("in_progress")):
            return False, "Cannot edit table settings during an active hand."

        table["max_players"] = _coerce_blackjack_lan_max_players(
            max_players,
            table.get("max_players", BLACKJACK_LAN_DEFAULT_MAX_PLAYERS_PER_TABLE),
        )
        table["min_bet"] = _coerce_blackjack_lan_bet_amount(
            min_bet,
            table.get("min_bet", BLACKJACK_LAN_DEFAULT_MIN_BET),
        )
        table["max_bet"] = _coerce_blackjack_lan_bet_amount(
            max_bet,
            table.get("max_bet", BLACKJACK_LAN_DEFAULT_MAX_BET),
            allow_none=True,
        )
        if allow_spectators is not None:
            table["allow_spectators"] = bool(allow_spectators)
        if spectators_require_password is not None:
            table["spectators_require_password"] = bool(spectators_require_password)
        if is_private is not None:
            table["is_private"] = bool(is_private)
        if password is not None:
            table["password"] = str(password)
        if table_name is not None:
            table["name"] = _normalize_blackjack_lan_table_name(table_name, normalized_id)
        new_name_key = _blackjack_lan_table_name_key(table.get("name", ""))
        for existing in lan_state.get("tables", []):
            if int(existing.get("id", -1)) == normalized_id:
                continue
            if _blackjack_lan_table_name_key(existing.get("name", "")) == new_name_key:
                return False, "A table with that name already exists."
        if bool(table.get("is_private", False)) and (not str(table.get("password", "")).strip()):
            return False, "Private tables must have a password."
        if bool(table.get("spectators_require_password", False)) and (not str(table.get("password", "")).strip()):
            return False, "Tables that require spectator passwords must have a password."
        if not bool(table.get("is_private", False)):
            if not bool(table.get("spectators_require_password", False)):
                table["password"] = ""
        _blackjack_lan_normalize_table_bet_limits(table)

        if len(table.get("players", [])) > int(table["max_players"]):
            return False, "Reduce player count before lowering max players."

        for player_name, player_state in list(table.get("player_states", {}).items()):
            if not isinstance(player_state, dict):
                continue
            bet = house_round_credit(player_state.get("bet", 0.0))
            if bet <= 0:
                continue
            allowed, _reason = _blackjack_lan_is_bet_allowed(table, bet)
            if not allowed:
                player_state["bet"] = 0.0
                player_state["status"] = "waiting"
                player_state["message"] = "Your bet was cleared due to updated table limits."

        table["last_updated_epoch"] = time.time()
        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        return True, "Table settings updated."


def update_blackjack_lan_global_settings(
    turn_timeout_seconds,
    timeout_penalty_percent,
    allow_spectators_by_default=None,
):
    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        settings = _normalize_blackjack_lan_settings(lan_state.get("settings", {}))
        try:
            timeout_value = int(turn_timeout_seconds)
        except (TypeError, ValueError):
            timeout_value = settings["turn_timeout_seconds"]
        settings["turn_timeout_seconds"] = max(5, timeout_value)
        try:
            penalty_value = float(timeout_penalty_percent)
        except (TypeError, ValueError):
            penalty_value = settings["timeout_penalty_percent"]
        settings["timeout_penalty_percent"] = max(0.0, min(100.0, penalty_value))
        if allow_spectators_by_default is not None:
            settings["allow_spectators_by_default"] = bool(allow_spectators_by_default)
        lan_state["settings"] = settings
        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        return True, "Multiplayer timeout settings updated."


def join_blackjack_lan_table(table_id, player_name, password=""):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return False, "Invalid table."
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player."
    normalized_player = player_name.strip()
    provided_password = ""
    if password is not None:
        provided_password = str(password)

    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        if normalized_player not in data.get("accounts", {}):
            return False, "You must be signed in to join."

        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        destination = _blackjack_lan_table_by_id(lan_state, normalized_id)
        if destination is None:
            return False, "Table not found."
        if bool(destination.get("is_private", False)):
            expected_password = str(destination.get("password", ""))
            if expected_password and provided_password != expected_password:
                return False, "Incorrect table password."

        for table in lan_state.get("tables", []):
            membership = _blackjack_lan_table_member_state(table, normalized_player)
            if membership is None:
                continue
            if int(table.get("id", -1)) == normalized_id:
                if membership == "pending":
                    return True, "You are already queued for this table."
                return True, "Already in this table."
            if bool(table.get("in_progress")):
                return False, "Leave your current active table before joining another."
            table["players"] = [player for player in table.get("players", []) if player != normalized_player]
            table["pending_players"] = [
                player for player in table.get("pending_players", []) if player != normalized_player
            ]
            table.get("player_states", {}).pop(normalized_player, None)
            if table.get("host") == normalized_player:
                table["host"] = table["players"][0] if table["players"] else None
            if not table["players"]:
                reset_table = _default_blackjack_lan_table(
                    table.get("id", 1),
                    settings=lan_state.get("settings", {}),
                )
                reset_table["name"] = _normalize_blackjack_lan_table_name(
                    table.get("name", reset_table.get("name", "")),
                    table.get("id", 1),
                )
                table.clear()
                table.update(reset_table)
            else:
                table["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_BETS
                table["last_updated_epoch"] = time.time()

        if normalized_player in destination.get("players", []):
            data["blackjack_lan"] = lan_state
            _write_data_unlocked(data)
            return True, "Already in this table."
        if normalized_player in destination.get("pending_players", []):
            data["blackjack_lan"] = lan_state
            _write_data_unlocked(data)
            return True, "You are already queued for this table."

        players = destination.get("players", [])
        pending_players = destination.get("pending_players", [])
        max_players = int(destination.get("max_players", BLACKJACK_LAN_DEFAULT_MAX_PLAYERS_PER_TABLE))
        if len(players) + len(pending_players) >= max_players:
            return False, "Table is full."

        if bool(destination.get("in_progress")):
            pending_players.append(normalized_player)
            destination["pending_players"] = pending_players
            _blackjack_lan_append_history(
                destination,
                f"{normalized_player} queued to join on the next hand.",
            )
            destination["last_updated_epoch"] = time.time()
            data["blackjack_lan"] = lan_state
            _write_data_unlocked(data)
            return True, "Hand in progress. You are queued to join at the next hand."

        players.append(normalized_player)
        destination["players"] = players
        destination.setdefault("player_states", {})[normalized_player] = _default_blackjack_lan_player_state()
        if not destination.get("host"):
            destination["host"] = normalized_player
        if destination.get("phase") == BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS:
            destination["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_BETS
        destination["last_updated_epoch"] = time.time()
        _blackjack_lan_append_history(destination, f"{normalized_player} joined the table.")

        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        return True, f"Joined table {normalized_id}."


def leave_blackjack_lan_table(table_id, player_name):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return False, "Invalid table."
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player."
    normalized_player = player_name.strip()

    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        table = _blackjack_lan_table_by_id(lan_state, normalized_id)
        if table is None:
            return False, "Table not found."
        players = table.get("players", [])
        pending_players = table.get("pending_players", [])
        membership = _blackjack_lan_table_member_state(table, normalized_player)
        if membership is None:
            return True, "You are not in this table."
        if membership == "pending":
            table["pending_players"] = [player for player in pending_players if player != normalized_player]
            _blackjack_lan_append_history(table, f"{normalized_player} left the join queue.")
            table["last_updated_epoch"] = time.time()
            data["blackjack_lan"] = lan_state
            _write_data_unlocked(data)
            return True, f"Removed from queue for table {normalized_id}."
        if bool(table.get("in_progress")):
            return False, "Cannot leave while a hand is in progress."

        table["players"] = [player for player in players if player != normalized_player]
        table.get("player_states", {}).pop(normalized_player, None)
        if table.get("host") == normalized_player:
            table["host"] = table["players"][0] if table["players"] else None
        _blackjack_lan_append_history(table, f"{normalized_player} left the table.")

        if not table["players"]:
            reset_table = _default_blackjack_lan_table(
                normalized_id,
                settings=lan_state.get("settings", {}),
            )
            reset_table["name"] = _normalize_blackjack_lan_table_name(
                table.get("name", reset_table.get("name", "")),
                normalized_id,
            )
            table.clear()
            table.update(reset_table)
        else:
            table["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_BETS
            table["in_progress"] = False
            table["turn_order"] = []
            table["turn_index"] = 0
            table["turn_started_epoch"] = 0.0
            table["dealer_cards"] = []
            table["deck"] = []
            table["last_updated_epoch"] = time.time()

        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        return True, f"Left table {normalized_id}."


def auto_remove_blackjack_lan_player(player_name):
    if not isinstance(player_name, str):
        return False, "Invalid player."
    normalized_player = player_name.strip()
    if not normalized_player:
        return False, "Invalid player."

    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        removed = _blackjack_lan_force_remove_player_unlocked(data, lan_state, normalized_player)
        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        if removed:
            return True, "Player was removed from active multiplayer table(s)."
        return True, "Player was not in any multiplayer table."


def set_blackjack_lan_player_bet(table_id, player_name, bet):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return False, "Invalid table."
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player."
    normalized_player = player_name.strip()
    try:
        normalized_bet = house_round_credit(float(bet))
    except Exception:
        return False, "Invalid bet."
    if normalized_bet <= 0:
        return False, "Bet must be greater than $0."

    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        table = _blackjack_lan_table_by_id(lan_state, normalized_id)
        if table is None:
            return False, "Table not found."
        if normalized_player not in table.get("players", []):
            return False, "Join this table first."
        if bool(table.get("in_progress")):
            return False, "Round already in progress."
        if table.get("phase") not in {
            BLACKJACK_LAN_PHASE_WAITING_FOR_BETS,
            BLACKJACK_LAN_PHASE_FINISHED,
            BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS,
        }:
            return False, "Cannot place a bet right now."
        allowed, reason = _blackjack_lan_is_bet_allowed(table, normalized_bet)
        if not allowed:
            return False, reason

        player_state = table.setdefault("player_states", {}).setdefault(
            normalized_player, _default_blackjack_lan_player_state()
        )
        player_state["bet"] = normalized_bet
        player_state["ready"] = False
        player_state["cards"] = []
        player_state["status"] = "bet_ready"
        player_state["result"] = None
        player_state["message"] = ""
        player_state["payout"] = 0.0
        player_state["is_natural"] = False
        player_state["penalty_charged"] = 0.0

        if table.get("phase") == BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS:
            table["phase"] = BLACKJACK_LAN_PHASE_WAITING_FOR_BETS
        table["last_updated_epoch"] = time.time()

        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        return True, f"Bet set to ${normalized_bet:.2f}."


def set_blackjack_lan_player_ready(table_id, player_name, ready=True):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return False, "Invalid table.", False
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player.", False
    normalized_player = player_name.strip()
    desired_ready = bool(ready)

    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        table = _blackjack_lan_table_by_id(lan_state, normalized_id)
        if table is None:
            return False, "Table not found.", False
        if normalized_player not in table.get("players", []):
            return False, "Join this table first.", False
        if bool(table.get("in_progress")):
            return False, "Round already in progress.", False
        if table.get("phase") not in {
            BLACKJACK_LAN_PHASE_WAITING_FOR_BETS,
            BLACKJACK_LAN_PHASE_FINISHED,
            BLACKJACK_LAN_PHASE_WAITING_FOR_PLAYERS,
        }:
            return False, "Cannot change ready state right now.", False

        player_state = table.setdefault("player_states", {}).setdefault(
            normalized_player, _default_blackjack_lan_player_state()
        )
        bet = house_round_credit(player_state.get("bet", 0.0))
        if desired_ready:
            if bet <= 0:
                return False, "Set your bet before marking ready.", False
            allowed, reason = _blackjack_lan_is_bet_allowed(table, bet)
            if not allowed:
                return False, reason, False
            player_state["status"] = "ready"
        else:
            player_state["status"] = "waiting"
        player_state["ready"] = desired_ready
        player_state["message"] = ""
        table["last_updated_epoch"] = time.time()

        ready_count, total_players = _blackjack_lan_ready_counts(table)
        if total_players > 0 and ready_count == total_players:
            started, start_message = _start_blackjack_lan_round_unlocked(data, table)
            if not started:
                data["blackjack_lan"] = lan_state
                _write_data_unlocked(data)
                return False, start_message, False
            data["blackjack_lan"] = lan_state
            _write_data_unlocked(data)
            return True, start_message, True

        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        if desired_ready:
            return True, "You are ready.", False
        return True, "You are no longer ready.", False


def _start_blackjack_lan_round_unlocked(data, table):
    active_players = []
    for player_name in table.get("players", []):
        player_state = table.setdefault("player_states", {}).setdefault(
            player_name, _default_blackjack_lan_player_state()
        )
        bet = house_round_credit(player_state.get("bet", 0.0))
        if bet <= 0:
            return False, f"{player_name} must set a bet before getting ready."
        allowed, reason = _blackjack_lan_is_bet_allowed(table, bet)
        if not allowed:
            return False, f"{player_name}: {reason}"
        account = data.get("accounts", {}).get(player_name)
        if not isinstance(account, dict):
            return False, f"Account for {player_name} was not found."
        account_settings = _normalize_account_settings(account.get("settings", {}))
        balance = house_round_balance(account.get("balance", 0.0))
        if (not bool(account_settings.get("allow_negative_balance", False))) and balance < bet:
            return False, f"{player_name} cannot cover bet ${bet:.2f}."
        active_players.append(player_name)
    if not active_players:
        return False, "At least one player must set a bet."

    for player_name in active_players:
        player_state = table["player_states"][player_name]
        bet = house_round_credit(player_state.get("bet", 0.0))
        account = data.get("accounts", {}).get(player_name)
        account["balance"] = house_round_balance(account.get("balance", 0.0) - bet)

    table["round"] = int(table.get("round", 0)) + 1
    table["in_progress"] = True
    table["phase"] = BLACKJACK_LAN_PHASE_PLAYER_TURNS
    table["deck"] = _blackjack_new_deck()
    table["dealer_cards"] = []
    table["turn_order"] = []
    table["turn_index"] = 0
    table["turn_started_epoch"] = 0.0
    table["last_updated_epoch"] = time.time()

    table["dealer_cards"].append(_blackjack_draw_card_from_table(table))
    table["dealer_cards"].append(_blackjack_draw_card_from_table(table))

    for player_name in table.get("players", []):
        player_state = table.setdefault("player_states", {}).setdefault(
            player_name, _default_blackjack_lan_player_state()
        )
        player_state["ready"] = False
        player_state["cards"] = []
        player_state["result"] = None
        player_state["message"] = ""
        player_state["payout"] = 0.0
        player_state["is_natural"] = False
        player_state["penalty_charged"] = 0.0
        bet = house_round_credit(player_state.get("bet", 0.0))
        if player_name not in active_players or bet <= 0:
            player_state["status"] = "sitting_out"
            continue
        player_state["cards"].append(_blackjack_draw_card_from_table(table))
        player_state["cards"].append(_blackjack_draw_card_from_table(table))
        player_state["is_natural"] = _blackjack_is_natural(player_state["cards"])
        if player_state["is_natural"]:
            player_state["status"] = "blackjack"
        else:
            player_state["status"] = "playing"
            table["turn_order"].append(player_name)

    if not table["turn_order"]:
        _blackjack_lan_finish_round_unlocked(data, table)
    else:
        table["turn_started_epoch"] = time.time()
        current_turn = _blackjack_lan_current_turn_player(table)
        if current_turn:
            _blackjack_lan_append_history(table, f"Round {table['round']} started. {current_turn}'s turn.")
        else:
            _blackjack_lan_append_history(table, f"Round {table['round']} started.")

    return True, f"Round {table['round']} started."


def start_blackjack_lan_round(table_id, started_by):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return False, "Invalid table."
    if not isinstance(started_by, str) or not started_by.strip():
        return False, "Invalid player."
    starter = started_by.strip()

    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        table = _blackjack_lan_table_by_id(lan_state, normalized_id)
        if table is None:
            return False, "Table not found."
        if starter not in table.get("players", []):
            return False, "Join this table first."
        if bool(table.get("in_progress")):
            return False, "Round already in progress."
        ready_count, total_players = _blackjack_lan_ready_counts(table)
        if total_players <= 0:
            return False, "No players are seated."
        if ready_count < total_players:
            return False, "All seated players must be ready before the round starts."

        started, message = _start_blackjack_lan_round_unlocked(data, table)
        if not started:
            return False, message
        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        return True, message


def blackjack_lan_player_action(table_id, player_name, action):
    normalized_id = _coerce_blackjack_table_id(table_id)
    if normalized_id is None:
        return False, "Invalid table."
    if not isinstance(player_name, str) or not player_name.strip():
        return False, "Invalid player."
    normalized_player = player_name.strip()
    normalized_action = str(action).strip().lower()
    if normalized_action not in {"hit", "stand"}:
        return False, "Invalid action."

    with _accounts_write_lock():
        data = _load_data_for_write_unlocked()
        lan_state = _normalize_blackjack_lan_state(data.get("blackjack_lan", {}))
        _blackjack_lan_enforce_timeouts_unlocked(data, lan_state)
        table = _blackjack_lan_table_by_id(lan_state, normalized_id)
        if table is None:
            return False, "Table not found."
        if table.get("phase") != BLACKJACK_LAN_PHASE_PLAYER_TURNS or not bool(table.get("in_progress")):
            return False, "No active player turn."

        current_turn_player = _blackjack_lan_current_turn_player(table)
        if current_turn_player != normalized_player:
            if current_turn_player is None:
                return False, "Turn state is unavailable."
            return False, f"It is currently {current_turn_player}'s turn."

        player_state = table.get("player_states", {}).get(normalized_player)
        if not isinstance(player_state, dict):
            return False, "Player state not found."
        if player_state.get("status") != "playing":
            return False, "You cannot act right now."

        if normalized_action == "hit":
            card = _blackjack_draw_card_from_table(table)
            player_state.setdefault("cards", []).append(card)
            player_total = _blackjack_hand_total(player_state["cards"])
            _blackjack_lan_append_history(table, f"{normalized_player} hit.")
            if player_total > 21:
                player_state["status"] = "busted"
                _blackjack_lan_append_history(table, f"{normalized_player} busted with {player_total}.")
                next_player = _blackjack_lan_advance_turn_unlocked(table)
                if next_player is not None:
                    _blackjack_lan_append_history(table, f"It is now {next_player}'s turn.")
            elif player_total == 21:
                player_state["status"] = "stood"
                next_player = _blackjack_lan_advance_turn_unlocked(table)
                if next_player is not None:
                    _blackjack_lan_append_history(table, f"It is now {next_player}'s turn.")
            else:
                table["turn_started_epoch"] = time.time()
        else:
            player_state["status"] = "stood"
            _blackjack_lan_append_history(table, f"{normalized_player} stood.")
            next_player = _blackjack_lan_advance_turn_unlocked(table)
            if next_player is not None:
                _blackjack_lan_append_history(table, f"It is now {next_player}'s turn.")

        if _blackjack_lan_current_turn_player(table) is None:
            _blackjack_lan_append_history(table, "Dealer turn.")
            _blackjack_lan_finish_round_unlocked(data, table)
        else:
            table["last_updated_epoch"] = time.time()

        data["blackjack_lan"] = lan_state
        _write_data_unlocked(data)
        return True, "Action submitted."
