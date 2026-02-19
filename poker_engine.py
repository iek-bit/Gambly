"""Core Texas Hold'em engine for single-player and LAN multiplayer."""

from __future__ import annotations

from itertools import combinations
from random import Random


RANKS = "23456789TJQKA"
SUITS = "SHDC"
RANK_TO_VALUE = {rank: index + 2 for index, rank in enumerate(RANKS)}

STREET_PRE_FLOP = "preflop"
STREET_FLOP = "flop"
STREET_TURN = "turn"
STREET_RIVER = "river"
STREET_SHOWDOWN = "showdown"
STREET_FINISHED = "finished"


def to_cents(amount):
    return int(round(float(amount) * 100.0))


def from_cents(amount_cents):
    return float(amount_cents) / 100.0


def _new_deck(rng):
    deck = [f"{r}{s}" for s in SUITS for r in RANKS]
    rng.shuffle(deck)
    return deck


def _rank_counts(cards):
    counts = {}
    for card in cards:
        rank = card[0]
        counts[rank] = counts.get(rank, 0) + 1
    return counts


def _is_straight(values):
    unique = sorted(set(values), reverse=True)
    if 14 in unique:
        unique.append(1)
    for idx in range(0, len(unique) - 4):
        window = unique[idx : idx + 5]
        if window[0] - window[4] == 4 and len(window) == 5:
            return True, window[0]
    return False, None


def evaluate_five(cards):
    values = sorted((RANK_TO_VALUE[c[0]] for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    flush = len(set(suits)) == 1
    straight, high_straight = _is_straight(values)
    rank_counts = _rank_counts(cards)
    groups = sorted(((count, RANK_TO_VALUE[rank]) for rank, count in rank_counts.items()), reverse=True)

    if straight and flush:
        return (8, high_straight)
    if groups[0][0] == 4:
        four = groups[0][1]
        kicker = max(value for value in values if value != four)
        return (7, four, kicker)
    if groups[0][0] == 3 and groups[1][0] == 2:
        return (6, groups[0][1], groups[1][1])
    if flush:
        return (5, *values)
    if straight:
        return (4, high_straight)
    if groups[0][0] == 3:
        trips = groups[0][1]
        kickers = sorted((value for value in values if value != trips), reverse=True)
        return (3, trips, *kickers)
    if groups[0][0] == 2 and groups[1][0] == 2:
        pair_high = max(groups[0][1], groups[1][1])
        pair_low = min(groups[0][1], groups[1][1])
        kicker = max(value for value in values if value not in {pair_high, pair_low})
        return (2, pair_high, pair_low, kicker)
    if groups[0][0] == 2:
        pair = groups[0][1]
        kickers = sorted((value for value in values if value != pair), reverse=True)
        return (1, pair, *kickers)
    return (0, *values)


def evaluate_best_seven(cards):
    best = None
    for combo in combinations(cards, 5):
        score = evaluate_five(combo)
        if best is None or score > best:
            best = score
    return best


def _next_active_index(players, start_index):
    count = len(players)
    for offset in range(1, count + 1):
        idx = (start_index + offset) % count
        player = players[idx]
        if (not player.get("folded", False)) and (not player.get("all_in", False)):
            return idx
    return None


def _next_seated_index(players, start_index):
    count = len(players)
    for offset in range(1, count + 1):
        idx = (start_index + offset) % count
        player = players[idx]
        if player.get("stack", 0) > 0:
            return idx
    return None


def _eligible_to_act_players(state):
    return [
        player["name"]
        for player in state["players"]
        if (not player.get("folded", False)) and (not player.get("all_in", False))
    ]


def _collect_uncontested(state):
    alive = [p for p in state["players"] if not p.get("folded", False)]
    if len(alive) != 1:
        return False
    winner = alive[0]
    pot = sum(int(player.get("committed_total", 0)) for player in state["players"])
    winner["stack"] += pot
    state["pot"] = 0
    state["street"] = STREET_FINISHED
    state["winner"] = winner["name"]
    state["result"] = {
        "type": "uncontested",
        "winners": {winner["name"]: pot},
        "pots": [{"amount": pot, "winners": [winner["name"]]}],
    }
    return True


def _build_side_pots(state):
    contrib = {p["name"]: int(p.get("committed_total", 0)) for p in state["players"]}
    levels = sorted({value for value in contrib.values() if value > 0})
    pots = []
    prev = 0
    for level in levels:
        participants = [name for name, value in contrib.items() if value >= level]
        amount = (level - prev) * len(participants)
        eligible = [
            name
            for name in participants
            if not next(player for player in state["players"] if player["name"] == name).get("folded", False)
        ]
        if amount > 0:
            pots.append({"amount": amount, "participants": participants, "eligible": eligible})
        prev = level
    return pots


def _distribute_cents(amount, winners, state):
    if not winners:
        return {}
    base = amount // len(winners)
    rem = amount % len(winners)
    payouts = {winner: base for winner in winners}
    if rem > 0:
        if state.get("dealer_index") is None:
            order = winners
        else:
            names = [p["name"] for p in state["players"]]
            start_idx = (state["dealer_index"] + 1) % len(names)
            ordered = names[start_idx:] + names[:start_idx]
            order = [name for name in ordered if name in winners]
        for name in order[:rem]:
            payouts[name] += 1
    return payouts


def run_showdown(state):
    pots = _build_side_pots(state)
    payouts = {}
    detail = []
    for pot in pots:
        eligible = pot["eligible"]
        if not eligible:
            continue
        ranked = []
        for name in eligible:
            player = next(p for p in state["players"] if p["name"] == name)
            score = evaluate_best_seven(player["hole"] + state["board"])
            ranked.append((score, name))
        ranked.sort(reverse=True)
        best_score = ranked[0][0]
        winners = [name for score, name in ranked if score == best_score]
        dist = _distribute_cents(pot["amount"], winners, state)
        for winner, gain in dist.items():
            payouts[winner] = payouts.get(winner, 0) + gain
        detail.append({"amount": pot["amount"], "winners": winners})

    for player in state["players"]:
        name = player["name"]
        player["stack"] += payouts.get(name, 0)

    state["pot"] = 0
    state["street"] = STREET_FINISHED
    state["result"] = {
        "type": "showdown",
        "winners": payouts,
        "pots": detail,
    }


def _deal_board_card(state, count):
    for _ in range(count):
        if state["deck"]:
            state["board"].append(state["deck"].pop())


def _start_next_street(state):
    alive = [p for p in state["players"] if not p.get("folded", False)]
    if len(alive) <= 1:
        _collect_uncontested(state)
        return
    if all(player.get("all_in", False) for player in alive):
        while len(state["board"]) < 5:
            if state["deck"]:
                state["deck"].pop()
            _deal_board_card(state, 1)
        state["street"] = STREET_SHOWDOWN
        run_showdown(state)
        return

    for player in state["players"]:
        player["street_commit"] = 0

    state["current_bet"] = 0
    state["min_raise"] = state.get("table_min_raise", state["big_blind"])

    if state["street"] == STREET_PRE_FLOP:
        if state["deck"]:
            state["deck"].pop()
        _deal_board_card(state, 3)
        state["street"] = STREET_FLOP
    elif state["street"] == STREET_FLOP:
        if state["deck"]:
            state["deck"].pop()
        _deal_board_card(state, 1)
        state["street"] = STREET_TURN
    elif state["street"] == STREET_TURN:
        if state["deck"]:
            state["deck"].pop()
        _deal_board_card(state, 1)
        state["street"] = STREET_RIVER
    elif state["street"] == STREET_RIVER:
        state["street"] = STREET_SHOWDOWN
        run_showdown(state)
        return

    pending = set(_eligible_to_act_players(state))
    state["pending_to_act"] = list(pending)
    start_idx = _next_active_index(state["players"], state["dealer_index"])
    state["acting_index"] = start_idx


def _maybe_advance(state):
    if state["street"] in {STREET_SHOWDOWN, STREET_FINISHED}:
        return
    if _collect_uncontested(state):
        return
    if not state.get("pending_to_act"):
        _start_next_street(state)
        return
    current_name = state["players"][state["acting_index"]]["name"]
    if current_name not in set(state.get("pending_to_act", [])):
        pending = set(state.get("pending_to_act", []))
        for _ in range(len(state["players"])):
            next_idx = _next_active_index(state["players"], state["acting_index"])
            if next_idx is None:
                break
            if state["players"][next_idx]["name"] in pending:
                state["acting_index"] = next_idx
                return
            state["acting_index"] = next_idx


def create_hand(player_stacks, small_blind, big_blind, min_raise=None, dealer_index=0, seed=None):
    rng = Random(seed)
    players = []
    for name, stack in player_stacks:
        stack_cents = to_cents(stack)
        players.append(
            {
                "name": str(name),
                "stack": max(0, stack_cents),
                "hole": [],
                "folded": False,
                "all_in": False,
                "street_commit": 0,
                "committed_total": 0,
            }
        )

    active = [index for index, player in enumerate(players) if player["stack"] > 0]
    if len(active) < 2:
        return None, "At least two players with chips are required."

    if dealer_index < 0 or dealer_index >= len(players):
        dealer_index = active[0]

    deck = _new_deck(rng)
    if min_raise is None:
        min_raise = big_blind
    state = {
        "players": players,
        "small_blind": max(1, to_cents(small_blind)),
        "big_blind": max(1, to_cents(big_blind)),
        "dealer_index": dealer_index,
        "deck": deck,
        "board": [],
        "street": STREET_PRE_FLOP,
        "current_bet": 0,
        "min_raise": max(1, to_cents(min_raise)),
        "table_min_raise": max(1, to_cents(min_raise)),
        "acting_index": None,
        "pending_to_act": [],
        "pot": 0,
        "result": None,
        "winner": None,
        "action_log": [],
    }

    for _ in range(2):
        for idx in range(len(players)):
            player = players[idx]
            if player["stack"] <= 0:
                continue
            player["hole"].append(deck.pop())

    sb_index = _next_seated_index(players, dealer_index)
    bb_index = _next_seated_index(players, sb_index)

    for blind_index, blind_amount in ((sb_index, state["small_blind"]), (bb_index, state["big_blind"])):
        player = players[blind_index]
        posted = min(player["stack"], blind_amount)
        player["stack"] -= posted
        player["street_commit"] += posted
        player["committed_total"] += posted
        if player["stack"] == 0:
            player["all_in"] = True

    state["current_bet"] = players[bb_index]["street_commit"]
    state["pot"] = sum(player["committed_total"] for player in players)

    pending = set(_eligible_to_act_players(state))
    state["pending_to_act"] = list(pending)
    state["acting_index"] = _next_active_index(players, bb_index)

    _maybe_advance(state)
    return state, None


def legal_actions(state, player_name):
    if not state or state.get("street") in {STREET_SHOWDOWN, STREET_FINISHED}:
        return {"actions": []}
    if state["players"][state.get("acting_index", 0)]["name"] != player_name:
        return {"actions": []}
    player = next((p for p in state["players"] if p["name"] == player_name), None)
    if not player or player.get("folded") or player.get("all_in"):
        return {"actions": []}

    to_call = max(0, state["current_bet"] - player.get("street_commit", 0))
    stack = player.get("stack", 0)
    actions = ["fold"]

    if to_call <= 0:
        actions.append("check")
        if stack > 0:
            min_bet = state["big_blind"]
            actions.append("bet")
            actions.append("all_in")
            return {
                "actions": actions,
                "to_call": from_cents(to_call),
                "min_bet": from_cents(min_bet),
                "max_bet": from_cents(stack),
            }
        return {"actions": actions, "to_call": 0.0}

    if stack > 0:
        actions.append("call")
        if stack > to_call:
            actions.append("raise")
            actions.append("all_in")
    return {
        "actions": actions,
        "to_call": from_cents(to_call),
        "min_raise_to": from_cents(state["current_bet"] + state["min_raise"]),
        "max_raise_to": from_cents(player.get("street_commit", 0) + stack),
    }


def apply_action(state, player_name, action, amount=None):
    normalized_action = str(action).strip().lower()
    if state.get("street") in {STREET_SHOWDOWN, STREET_FINISHED}:
        return False, "Hand already finished."
    actor_idx = state.get("acting_index")
    if actor_idx is None:
        return False, "No active player turn."
    actor = state["players"][actor_idx]
    if actor["name"] != player_name:
        return False, "Not your turn."
    if actor.get("folded") or actor.get("all_in"):
        return False, "You cannot act right now."

    to_call = max(0, state["current_bet"] - actor.get("street_commit", 0))
    pending = set(state.get("pending_to_act", []))

    if normalized_action == "fold":
        actor["folded"] = True
        pending.discard(player_name)
    elif normalized_action == "check":
        if to_call != 0:
            return False, "Cannot check facing a bet."
        pending.discard(player_name)
    elif normalized_action == "call":
        if to_call <= 0:
            return False, "Nothing to call."
        pay = min(actor["stack"], to_call)
        actor["stack"] -= pay
        actor["street_commit"] += pay
        actor["committed_total"] += pay
        if actor["stack"] == 0:
            actor["all_in"] = True
        pending.discard(player_name)
    elif normalized_action == "bet":
        if to_call != 0:
            return False, "Use raise while facing a bet."
        try:
            bet_to = to_cents(amount)
        except Exception:
            return False, "Invalid bet amount."
        if bet_to <= 0:
            return False, "Bet must be positive."
        if bet_to > actor["stack"]:
            return False, "Insufficient chips for this bet."
        if bet_to < state["big_blind"] and bet_to < actor["stack"]:
            return False, "Bet is below minimum."
        actor["stack"] -= bet_to
        actor["street_commit"] += bet_to
        actor["committed_total"] += bet_to
        if actor["stack"] == 0:
            actor["all_in"] = True
        state["current_bet"] = actor["street_commit"]
        state["min_raise"] = max(state["big_blind"], bet_to)
        pending = set(_eligible_to_act_players(state))
        pending.discard(player_name)
    elif normalized_action == "raise":
        if to_call <= 0:
            return False, "Nothing to raise."
        try:
            raise_to = to_cents(amount)
        except Exception:
            return False, "Invalid raise amount."
        min_to = state["current_bet"] + state["min_raise"]
        max_to = actor["street_commit"] + actor["stack"]
        if raise_to > max_to:
            return False, "Insufficient chips for this raise."
        is_all_in = raise_to == max_to
        if raise_to < min_to and not is_all_in:
            return False, "Raise is below minimum."
        pay = raise_to - actor["street_commit"]
        if pay <= 0:
            return False, "Raise must increase commitment."
        actor["stack"] -= pay
        actor["street_commit"] += pay
        actor["committed_total"] += pay
        if actor["stack"] == 0:
            actor["all_in"] = True
        full_raise = raise_to - state["current_bet"]
        if full_raise >= state["min_raise"]:
            state["min_raise"] = full_raise
        state["current_bet"] = raise_to
        pending = set(_eligible_to_act_players(state))
        pending.discard(player_name)
    elif normalized_action == "all_in":
        if actor["stack"] <= 0:
            return False, "No chips remaining."
        added = actor["stack"]
        actor["stack"] = 0
        actor["street_commit"] += added
        actor["committed_total"] += added
        actor["all_in"] = True

        if actor["street_commit"] > state["current_bet"]:
            full_raise = actor["street_commit"] - state["current_bet"]
            state["current_bet"] = actor["street_commit"]
            if full_raise >= state["min_raise"]:
                state["min_raise"] = full_raise
                pending = set(_eligible_to_act_players(state))
                pending.discard(player_name)
            else:
                pending.discard(player_name)
        else:
            pending.discard(player_name)
    else:
        return False, "Invalid action."

    state["pending_to_act"] = list(pending)
    state["pot"] = sum(player.get("committed_total", 0) for player in state["players"])
    state.setdefault("action_log", []).append(
        {
            "player": player_name,
            "street": state["street"],
            "action": normalized_action,
            "amount": from_cents(to_cents(amount)) if amount is not None else None,
        }
    )

    if state.get("street") not in {STREET_SHOWDOWN, STREET_FINISHED}:
        next_idx = _next_active_index(state["players"], actor_idx)
        if next_idx is not None:
            state["acting_index"] = next_idx

    _maybe_advance(state)
    return True, "Action accepted."


def state_to_public(state, viewer_name=None, reveal_all=False):
    view = {
        "street": state.get("street"),
        "board": list(state.get("board", [])),
        "pot": from_cents(state.get("pot", 0)),
        "current_bet": from_cents(state.get("current_bet", 0)),
        "min_raise": from_cents(state.get("min_raise", 0)),
        "acting_player": None,
        "players": [],
        "result": state.get("result"),
        "action_log": list(state.get("action_log", [])),
        "dealer_index": state.get("dealer_index", 0),
    }
    idx = state.get("acting_index")
    if idx is not None and 0 <= idx < len(state.get("players", [])):
        view["acting_player"] = state["players"][idx]["name"]
    for player in state.get("players", []):
        show_cards = reveal_all or player["name"] == viewer_name or state.get("street") == STREET_FINISHED
        view["players"].append(
            {
                "name": player["name"],
                "stack": from_cents(player.get("stack", 0)),
                "hole": list(player.get("hole", [])) if show_cards else ["??", "??"],
                "folded": bool(player.get("folded", False)),
                "all_in": bool(player.get("all_in", False)),
                "street_commit": from_cents(player.get("street_commit", 0)),
                "committed_total": from_cents(player.get("committed_total", 0)),
            }
        )
    return view
