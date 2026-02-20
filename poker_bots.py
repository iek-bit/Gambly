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


def _bot_profile(player_name):
    # Stable per-name style so bots feel distinct without maintaining extra state.
    seed = sum(ord(ch) for ch in str(player_name))
    looseness = ((seed % 21) - 10) / 100.0  # -0.10..+0.10
    aggression = (((seed // 7) % 21) - 10) / 100.0  # -0.10..+0.10
    return looseness, aggression


def _hand_category_value(hole_cards, board_cards):
    cards = list(hole_cards) + list(board_cards)
    if len(cards) < 5:
        return 0
    return int(evaluate_best_seven(cards)[0])


def _has_flush_draw(hole_cards, board_cards):
    cards = list(hole_cards) + list(board_cards)
    if len(cards) < 4:
        return False
    suit_counts = {}
    for card in cards:
        suit_counts[card[1]] = suit_counts.get(card[1], 0) + 1
    return max(suit_counts.values()) >= 4


def _has_straight_draw(hole_cards, board_cards):
    cards = list(hole_cards) + list(board_cards)
    if len(cards) < 4:
        return False
    values = {RANK_TO_VALUE[card[0]] for card in cards}
    if 14 in values:
        values.add(1)
    sorted_vals = sorted(values)
    # Lightweight draw detection: any 4-card window that is close enough.
    for idx in range(0, len(sorted_vals) - 3):
        window = sorted_vals[idx : idx + 4]
        if window[-1] - window[0] <= 4:
            return True
    return False


def _strength_0_100(state, player):
    hole = list(player.get("hole", []))
    board = list(state.get("board", []))
    if len(hole) != 2:
        return 0.0, 0.0

    if not board:
        ranks = sorted([RANK_TO_VALUE[c[0]] for c in hole], reverse=True)
        suited = hole[0][1] == hole[1][1]
        gap = abs(ranks[0] - ranks[1])
        pair = ranks[0] == ranks[1]

        score = (ranks[0] + ranks[1]) * 2.0
        if pair:
            score += 30.0 + (ranks[0] * 1.5)
        if suited:
            score += 4.0
        if gap == 1:
            score += 4.0
        elif gap == 2:
            score += 2.0
        elif gap >= 4:
            score -= 3.0
        if ranks[0] >= 11 and ranks[1] >= 10:
            score += 6.0
        score = max(0.0, min(100.0, score))
        return score, 0.0

    category = _hand_category_value(hole, board)
    category_scale = {
        0: 22.0,  # high card
        1: 40.0,  # pair
        2: 57.0,  # two pair
        3: 70.0,  # trips
        4: 80.0,  # straight
        5: 86.0,  # flush
        6: 92.0,  # full house
        7: 97.0,  # quads
        8: 99.0,  # straight flush
    }
    base = category_scale.get(category, 20.0)
    kicker = evaluate_best_seven(hole + board)
    kicker_bonus = min(8.0, (sum(kicker[1:]) / max(1, len(kicker) - 1)) / 3.0)
    draw_bonus = 0.0
    if category <= 1:
        if _has_flush_draw(hole, board):
            draw_bonus += 7.0
        if _has_straight_draw(hole, board):
            draw_bonus += 5.0
    score = max(0.0, min(100.0, base + kicker_bonus + draw_bonus))
    return score, draw_bonus


def choose_bot_action(state, player_name, legal_info):
    actions = legal_info.get("actions", [])
    if not actions:
        return "check", None

    player = next((p for p in state.get("players", []) if p.get("name") == player_name), None)
    if not player:
        return "fold", None

    strength, draw_bonus = _strength_0_100(state, player)
    looseness, aggression = _bot_profile(player_name)

    to_call = float(legal_info.get("to_call", 0.0) or 0.0)
    pot = float(state.get("pot", 0.0) or 0.0)
    stack = float(player.get("stack", 0.0) or 0.0)
    board_len = len(state.get("board", []))
    preflop = board_len == 0
    commitment_ratio = to_call / max(0.01, stack)
    pot_odds = to_call / max(0.01, pot + to_call)
    action_log = state.get("action_log", [])
    recent_aggression = 0
    if isinstance(action_log, list):
        for entry in action_log[-4:]:
            if str(entry.get("action", "")).lower() in {"bet", "raise", "all_in"}:
                recent_aggression += 1

    if "check" in actions and to_call <= 0:
        if "all_in" in actions and stack > 0 and strength >= (95 - (aggression * 20)):
            return "all_in", None
        if "bet" in actions:
            bluff_factor = max(0.0, min(1.0, 0.12 + aggression + (0.06 if preflop else 0.0)))
            value_threshold = 56 - (aggression * 10) - (draw_bonus * 0.5)
            should_bet = strength >= value_threshold or (draw_bonus >= 5 and random.random() < bluff_factor)
            if should_bet:
                max_bet = min(float(legal_info.get("max_bet", stack) or stack), stack)
                min_bet = float(legal_info.get("min_bet", 0.0) or 0.0)
                if strength >= 86:
                    pot_mult = 0.95
                elif strength >= 72:
                    pot_mult = 0.72
                elif draw_bonus >= 5:
                    pot_mult = 0.48
                else:
                    pot_mult = 0.55
                size = max(min_bet, min(max_bet, max(pot * pot_mult, stack * 0.14)))
                return "bet", round(size, 2)
        return "check", None

    if "all_in" in actions and stack > 0:
        # Jam short stacks wider; otherwise reserve for very strong/value-heavy spots.
        if commitment_ratio >= 0.45 and strength >= (63 - (looseness * 20)):
            return "all_in", None
        if strength >= (97 - (aggression * 25)):
            return "all_in", None

    if "raise" in actions:
        min_to = float(legal_info.get("min_raise_to", 0.0) or 0.0)
        max_to = float(legal_info.get("max_raise_to", 0.0) or 0.0)
        raise_threshold = 69 + (commitment_ratio * 10) + (recent_aggression * 2) - (aggression * 14) - (looseness * 8)
        if preflop:
            raise_threshold += 2.5
        if strength >= raise_threshold and max_to >= min_to:
            if strength >= 88:
                raise_pot_mult = 1.08
            elif strength >= 78:
                raise_pot_mult = 0.86
            else:
                raise_pot_mult = 0.68
            target = max(min_to, min(max_to, max(to_call * 2.25, pot * raise_pot_mult)))
            return "raise", round(target, 2)

    if "call" in actions:
        call_threshold = (
            (50.0 if preflop else 44.0)
            + (commitment_ratio * 24.0)
            + (pot_odds * 18.0)
            + (recent_aggression * 1.5)
            - (draw_bonus * 0.75)
            - (looseness * 16.0)
            - (aggression * 8.0)
        )
        if strength >= call_threshold:
            return "call", None

    if "check" in actions:
        return "check", None
    if "fold" in actions:
        return "fold", None
    return actions[0], None
