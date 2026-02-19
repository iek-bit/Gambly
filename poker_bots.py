"""Rule-based poker bots for Texas Hold'em."""

from __future__ import annotations

import random

from poker_engine import RANK_TO_VALUE, evaluate_best_seven


def _preflop_strength(hole_cards):
    ranks = sorted([RANK_TO_VALUE[c[0]] for c in hole_cards], reverse=True)
    suited = hole_cards[0][1] == hole_cards[1][1]
    gap = abs(ranks[0] - ranks[1])
    pair = ranks[0] == ranks[1]

    score = ranks[0] + ranks[1]
    if pair:
        score += 18
    if suited:
        score += 3
    if gap == 1:
        score += 2
    elif gap == 0:
        score += 1
    elif gap >= 4:
        score -= 2
    return score


def _postflop_strength(hole_cards, board_cards):
    cards = hole_cards + board_cards
    if len(cards) < 5:
        return _preflop_strength(hole_cards)
    score = evaluate_best_seven(cards)
    category = score[0]
    kicker_bonus = sum(score[1:]) / 100.0
    return 20 + (category * 8) + kicker_bonus


def choose_bot_action(state, player_name, legal_info):
    actions = legal_info.get("actions", [])
    if not actions:
        return "check", None

    player = next((p for p in state.get("players", []) if p.get("name") == player_name), None)
    if not player:
        return "fold", None

    board = state.get("board", [])
    hole = player.get("hole", [])

    if len(board) == 0:
        strength = _preflop_strength(hole)
    else:
        strength = _postflop_strength(hole, board)

    to_call = float(legal_info.get("to_call", 0.0) or 0.0)
    pot = float(state.get("pot", 0.0) or 0.0)
    stack = float(player.get("stack", 0.0) or 0.0)

    if "check" in actions and to_call <= 0:
        if "bet" in actions and strength > 36 and random.random() < 0.55:
            max_bet = min(float(legal_info.get("max_bet", stack)), stack)
            min_bet = float(legal_info.get("min_bet", 0.0) or 0.0)
            size = max(min_bet, min(max_bet, max(pot * 0.55, stack * 0.2)))
            return "bet", round(size, 2)
        if "all_in" in actions and strength > 44 and random.random() < 0.2:
            return "all_in", None
        return "check", None

    pot_odds = to_call / max(0.01, pot + to_call)

    if "raise" in actions and strength > 42 and random.random() < 0.65:
        min_to = float(legal_info.get("min_raise_to", 0.0) or 0.0)
        max_to = float(legal_info.get("max_raise_to", 0.0) or 0.0)
        target = max(min_to, min(max_to, max(pot * 0.8, to_call * 2.2)))
        if target >= min_to:
            return "raise", round(target, 2)

    if "all_in" in actions and strength > 50 and random.random() < 0.3:
        return "all_in", None

    if "call" in actions:
        call_threshold = 30 + (8 if pot_odds < 0.25 else 0) - (8 if pot_odds > 0.45 else 0)
        if strength >= call_threshold:
            return "call", None

    if "check" in actions:
        return "check", None
    if "fold" in actions:
        return "fold", None
    return actions[0], None
