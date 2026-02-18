"""Streamlit frontend for the Number Guessing Gambling Game."""

from random import randint, shuffle
import uuid
import time
import math

import streamlit as st
import streamlit.components.v1 as components
import base64

from logout_handler import start_logout_server
from gameplay import calculate_payout
from money_utils import format_money, house_round_charge, house_round_credit

# Start the logout handler server once
_logout_server_started = False
from storage import (
    add_account_value,
    acquire_account_session,
    auto_remove_blackjack_lan_player,
    blackjack_lan_player_action,
    can_spectate_blackjack_lan_table,
    create_blackjack_lan_table,
    create_account_record,
    delete_blackjack_lan_table,
    delete_account,
    find_blackjack_lan_table_for_player,
    force_acquire_account_session,
    get_account_admin_status,
    get_account_stats,
    get_account_settings,
    get_account_password,
    get_accounts_snapshot,
    get_account_value,
    get_blackjack_lan_settings,
    get_blackjack_lan_tables,
    is_reserved_account_name,
    join_blackjack_lan_table,
    leave_blackjack_lan_table,
    list_account_names,
    load_game_limits,
    load_saved_odds,
    record_game_result,
    save_game_limits,
    save_odds,
    set_blackjack_lan_player_ready,
    set_blackjack_lan_player_bet,
    set_account_admin_status,
    set_account_settings,
    set_account_value,
    set_account_password,
    update_blackjack_lan_global_settings,
    update_blackjack_lan_table_settings,
    release_account_session,
)

ADMIN_ACCOUNT_NAME = "isaac"
BLACKJACK_DEALER_STAND_TOTAL = 17
BLACKJACK_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
BLACKJACK_SUITS = ["S", "H", "D", "C"]
STAT_SCOPE_OPTIONS = {
    "All games": None,
    "Number guessing (you guess)": "player_guess",
    "Number guessing (computer guesses)": "computer_guess",
    "Blackjack": "blackjack",
}
AVATAR_OPTIONS = [
    ("fox", "🦊", "Fox", "animal wild clever"),
    ("wolf", "🐺", "Wolf", "animal wild pack"),
    ("lion", "🦁", "Lion", "animal king jungle"),
    ("tiger", "🐯", "Tiger", "animal striped jungle"),
    ("cat", "🐱", "Cat", "animal pet"),
    ("dog", "🐶", "Dog", "animal pet"),
    ("rabbit", "🐰", "Rabbit", "animal bunny"),
    ("panda", "🐼", "Panda", "animal bamboo"),
    ("koala", "🐨", "Koala", "animal australia"),
    ("bear", "🐻", "Bear", "animal forest"),
    ("polar_bear", "🐻‍❄️", "Polar Bear", "animal arctic snow"),
    ("monkey", "🐵", "Monkey", "animal jungle"),
    ("gorilla", "🦍", "Gorilla", "animal ape"),
    ("unicorn", "🦄", "Unicorn", "fantasy magical"),
    ("dragon", "🐉", "Dragon", "fantasy fire"),
    ("phoenix", "🐦‍🔥", "Phoenix", "fantasy fire bird"),
    ("dino", "🦖", "Dinosaur", "dino prehistoric"),
    ("octopus", "🐙", "Octopus", "ocean sea"),
    ("shark", "🦈", "Shark", "ocean sea"),
    ("dolphin", "🐬", "Dolphin", "ocean sea"),
    ("whale", "🐳", "Whale", "ocean sea"),
    ("penguin", "🐧", "Penguin", "bird arctic"),
    ("eagle", "🦅", "Eagle", "bird sky"),
    ("owl", "🦉", "Owl", "bird night"),
    ("crow", "🐦", "Crow", "bird"),
    ("butterfly", "🦋", "Butterfly", "insect colorful"),
    ("bee", "🐝", "Bee", "insect honey"),
    ("ladybug", "🐞", "Ladybug", "insect"),
    ("snail", "🐌", "Snail", "animal slow"),
    ("frog", "🐸", "Frog", "animal"),
    ("lizard", "🦎", "Lizard", "animal reptile"),
    ("snake", "🐍", "Snake", "animal reptile"),
    ("turtle", "🐢", "Turtle", "animal ocean"),
    ("horse", "🐴", "Horse", "animal"),
    ("zebra", "🦓", "Zebra", "animal striped"),
    ("deer", "🦌", "Deer", "animal forest"),
    ("boar", "🐗", "Boar", "animal forest"),
    ("elephant", "🐘", "Elephant", "animal"),
    ("rhino", "🦏", "Rhino", "animal"),
    ("hippo", "🦛", "Hippo", "animal"),
    ("camel", "🐫", "Camel", "animal desert"),
    ("sloth", "🦥", "Sloth", "animal"),
    ("otter", "🦦", "Otter", "animal river"),
    ("raccoon", "🦝", "Raccoon", "animal"),
    ("chipmunk", "🐿️", "Chipmunk", "animal"),
    ("hamster", "🐹", "Hamster", "animal pet"),
    ("cow", "🐮", "Cow", "animal farm"),
    ("pig", "🐷", "Pig", "animal farm"),
    ("goat", "🐐", "Goat", "animal farm"),
    ("sheep", "🐑", "Sheep", "animal farm"),
    ("chicken", "🐔", "Chicken", "animal farm"),
    ("duck", "🦆", "Duck", "animal bird"),
    ("wizard", "🧙", "Wizard", "fantasy mage"),
    ("vampire", "🧛", "Vampire", "fantasy night"),
    ("elf", "🧝", "Elf", "fantasy"),
    ("ninja", "🥷", "Ninja", "fighter stealth"),
    ("rockstar", "🧑‍🎤", "Rock Star", "music performer"),
    ("astronaut", "🧑‍🚀", "Astronaut", "space rocket"),
    ("pilot", "🧑‍✈️", "Pilot", "flight sky"),
    ("artist", "🧑‍🎨", "Artist", "paint creative"),
    ("chef", "🧑‍🍳", "Chef", "cook food"),
    ("scientist", "🧑‍🔬", "Scientist", "lab science"),
    ("teacher", "🧑‍🏫", "Teacher", "school"),
    ("judge", "🧑‍⚖️", "Judge", "law"),
    ("detective", "🕵️", "Detective", "mystery"),
    ("guard", "💂", "Guard", "royal"),
    ("superhero", "🦸", "Superhero", "hero comic"),
    ("mage", "🧙‍♂️", "Mage", "fantasy wizard"),
    ("robot", "🤖", "Robot", "tech ai"),
    ("alien", "👽", "Alien", "space ufo"),
    ("ghost", "👻", "Ghost", "spooky"),
    ("skull", "💀", "Skull", "spooky"),
    ("devil", "😈", "Devil", "spooky"),
    ("cool", "😎", "Cool Face", "sunglasses"),
    ("nerd", "🤓", "Nerd Face", "glasses"),
    ("mind_blown", "🤯", "Mind Blown", "wow"),
    ("party", "🥳", "Party Face", "celebration"),
    ("laugh", "😂", "Laugh Cry", "funny"),
    ("wink", "😉", "Wink", "smile"),
    ("sunglasses", "🕶️", "Shades", "cool"),
    ("star", "⭐", "Star", "sparkle"),
    ("sparkles", "✨", "Sparkles", "shine"),
    ("fire", "🔥", "Fire", "hot"),
    ("lightning", "⚡", "Lightning", "energy"),
    ("rainbow", "🌈", "Rainbow", "color"),
    ("sun", "🌞", "Sun", "day"),
    ("moon", "🌙", "Moon", "night"),
    ("planet", "🪐", "Planet", "space"),
    ("comet", "☄️", "Comet", "space"),
    ("diamond", "💎", "Diamond", "gem"),
    ("crown", "👑", "Crown", "royal"),
    ("money_bag", "💰", "Money Bag", "cash"),
    ("coin", "🪙", "Coin", "money"),
    ("dice", "🎲", "Dice", "game"),
    ("cards", "🃏", "Joker Card", "casino"),
    ("spade", "♠️", "Spade", "cards casino"),
    ("heart", "❤️", "Heart", "love"),
    ("gem", "🔷", "Blue Gem", "shape"),
    ("soccer", "⚽", "Soccer", "sports"),
    ("basketball", "🏀", "Basketball", "sports"),
    ("football", "🏈", "Football", "sports"),
    ("baseball", "⚾", "Baseball", "sports"),
    ("gamepad", "🎮", "Gamepad", "gaming"),
    ("joystick", "🕹️", "Joystick", "gaming arcade"),
    ("headphones", "🎧", "Headphones", "music"),
    ("guitar", "🎸", "Guitar", "music"),
    ("drum", "🥁", "Drum", "music"),
    ("microphone", "🎤", "Microphone", "music"),
    ("pizza", "🍕", "Pizza", "food"),
    ("burger", "🍔", "Burger", "food"),
    ("fries", "🍟", "Fries", "food"),
    ("taco", "🌮", "Taco", "food"),
    ("sushi", "🍣", "Sushi", "food"),
    ("apple", "🍎", "Apple", "fruit"),
    ("watermelon", "🍉", "Watermelon", "fruit"),
    ("cherry", "🍒", "Cherry", "fruit"),
    ("grapes", "🍇", "Grapes", "fruit"),
    ("coffee", "☕", "Coffee", "drink"),
    ("boba", "🧋", "Boba", "drink"),
]
AVATAR_OPTION_BY_ID = {avatar_id: (emoji, name, tags) for avatar_id, emoji, name, tags in AVATAR_OPTIONS}
AVATAR_CATEGORIES = [
    ("animals", "Animals", ["animal", "bird", "insect", "ocean", "reptile", "farm", "dino"]),
    ("fantasy", "Fantasy & Spooky", ["fantasy", "wizard", "mage", "ghost", "spooky", "devil"]),
    ("music", "Music", ["music", "guitar", "drum", "microphone", "headphones", "performer"]),
    (
        "people",
        "People & Characters",
        ["fighter", "astronaut", "pilot", "artist", "chef", "scientist", "teacher", "judge", "detective", "guard"],
    ),
    ("faces", "Faces", ["face", "smile", "wink", "funny", "cool", "glasses", "party", "wow"]),
    ("space_nature", "Space & Nature", ["space", "planet", "comet", "sun", "moon", "rainbow", "star", "sparkle"]),
    ("games_money", "Games & Money", ["game", "gaming", "arcade", "casino", "cards", "dice", "spade", "cash", "money"]),
    ("sports", "Sports", ["sports", "soccer", "basketball", "football", "baseball"]),
    ("food_drink", "Food & Drink", ["food", "fruit", "drink", "coffee", "boba", "pizza", "burger", "sushi", "taco"]),
]


def _default_ui_settings():
    return {
        "allow_negative_balance": False,
        "dark_mode": True,
        "enable_animations": True,
        "confirm_before_bet": True,
        "profile_avatar": "",
    }


def _apply_ui_settings_to_session(settings):
    merged = _default_ui_settings()
    if isinstance(settings, dict):
        merged.update(
            {
                "allow_negative_balance": bool(
                    settings.get("allow_negative_balance", merged["allow_negative_balance"])
                ),
                "dark_mode": bool(settings.get("dark_mode", merged["dark_mode"])),
                "enable_animations": bool(settings.get("enable_animations", merged["enable_animations"])),
                "confirm_before_bet": bool(settings.get("confirm_before_bet", merged["confirm_before_bet"])),
                "profile_avatar": str(settings.get("profile_avatar", merged["profile_avatar"])).strip(),
            }
        )
    # Apply merged settings to session state
    st.session_state["setting_allow_negative_balance"] = merged["allow_negative_balance"]
    st.session_state["setting_dark_mode"] = merged["dark_mode"]
    st.session_state["setting_enable_animations"] = merged["enable_animations"]
    st.session_state["setting_confirm_before_bet"] = merged["confirm_before_bet"]
    st.session_state["setting_profile_avatar"] = merged["profile_avatar"]


def _current_ui_settings_from_session():
    return {
        "allow_negative_balance": bool(st.session_state.get("setting_allow_negative_balance", False)),
        "dark_mode": bool(st.session_state.get("setting_dark_mode", True)),
        "enable_animations": bool(st.session_state.get("setting_enable_animations", True)),
        "confirm_before_bet": bool(st.session_state.get("setting_confirm_before_bet", True)),
        "profile_avatar": str(st.session_state.get("setting_profile_avatar", "")).strip(),
    }


def _profile_avatar_trigger_text(account_name):
    avatar_id = str(st.session_state.get("setting_profile_avatar", "")).strip()
    avatar_data = AVATAR_OPTION_BY_ID.get(avatar_id)
    if avatar_data:
        return avatar_data[0]
    if account_name:
        return account_name[0].upper()
    return "?"


def _profile_avatar_display_text(account_name):
    avatar_id = str(st.session_state.get("setting_profile_avatar", "")).strip()
    avatar_data = AVATAR_OPTION_BY_ID.get(avatar_id)
    if avatar_data:
        return f"{avatar_data[0]} {avatar_data[1]}"
    if account_name:
        return f"{account_name[0].upper()} (initial)"
    return "No avatar"


def _avatar_category_slug(avatar_id, name, tags):
    searchable = f"{avatar_id} {name} {tags}".lower()
    for slug, _label, keywords in AVATAR_CATEGORIES:
        if any(keyword in searchable for keyword in keywords):
            return slug
    return "misc"


def _group_avatar_options(search_query):
    normalized_query = search_query.strip().lower()
    category_labels = {slug: label for slug, label, _keywords in AVATAR_CATEGORIES}
    category_labels["misc"] = "Other"
    grouped = {slug: [] for slug in category_labels}

    for avatar_id, emoji, name, tags in AVATAR_OPTIONS:
        searchable = f"{avatar_id} {name} {tags} {emoji}".lower()
        if normalized_query and normalized_query not in searchable:
            continue
        category_slug = _avatar_category_slug(avatar_id, name, tags)
        grouped[category_slug].append((avatar_id, emoji, name))

    ordered_groups = []
    for slug, label, _keywords in AVATAR_CATEGORIES:
        if grouped[slug]:
            ordered_groups.append((slug, label, grouped[slug]))
    if grouped["misc"]:
        ordered_groups.append(("misc", "Other", grouped["misc"]))
    total_count = sum(len(items) for _slug, _label, items in ordered_groups)
    return ordered_groups, total_count


def _render_avatar_category_nav(category_groups):
    nav_links = []
    for slug, label, items in category_groups:
        nav_links.append(
            f'<a class="avatar-nav-link" href="#avatar-category-{slug}">{label} ({len(items)})</a>'
        )
    if not nav_links:
        return
    avatar_nav_color = st.session_state.get("theme_avatar_nav_color", "#e7f8f2")
    st.markdown(
        f"""
        <style>
        .avatar-nav-wrap {{
            position: sticky;
            top: 0.5rem;
            z-index: 15;
            margin: 0.1rem 0 0.9rem 0;
            padding: 0.42rem 0.5rem;
            border-radius: 14px;
            border: 1px solid rgba(119, 205, 178, 0.35);
            background: rgba(8, 26, 23, 0.76);
            backdrop-filter: blur(7px);
            overflow-x: auto;
            white-space: nowrap;
        }}

        .avatar-nav-link {{
            display: inline-block;
            margin: 0 0.35rem 0.22rem 0;
            padding: 0.34rem 0.62rem;
            border-radius: 999px;
            border: 1px solid rgba(144, 225, 196, 0.40);
            background: rgba(22, 74, 61, 0.7);
            color: {avatar_nav_color} !important;
            text-decoration: none !important;
            font-size: 0.86rem;
            font-weight: 700;
        }}

        .avatar-nav-link:hover {{
            filter: brightness(1.06);
        }}
        </style>
        <div class="avatar-nav-wrap">
            {''.join(nav_links)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _persist_ui_settings_for_current_account():
    account = st.session_state.get("current_account")
    if not account:
        return
    current_settings = _current_ui_settings_from_session()
    if set_account_settings(account, current_settings):
        st.session_state["persisted_ui_settings_snapshot"] = current_settings


def _sync_settings_controls_from_session():
    st.session_state["settings_control_allow_negative_balance"] = bool(
        st.session_state.get("setting_allow_negative_balance", False)
    )
    st.session_state["settings_control_dark_mode"] = bool(st.session_state.get("setting_dark_mode", True))
    st.session_state["settings_control_enable_animations"] = bool(
        st.session_state.get("setting_enable_animations", True)
    )
    st.session_state["settings_control_confirm_before_bet"] = bool(
        st.session_state.get("setting_confirm_before_bet", True)
    )


def _persist_ui_settings_from_controls():
    st.session_state["setting_allow_negative_balance"] = bool(
        st.session_state.get("settings_control_allow_negative_balance", False)
    )
    st.session_state["setting_dark_mode"] = bool(st.session_state.get("settings_control_dark_mode", True))
    st.session_state["setting_enable_animations"] = bool(
        st.session_state.get("settings_control_enable_animations", True)
    )
    st.session_state["setting_confirm_before_bet"] = bool(
        st.session_state.get("settings_control_confirm_before_bet", True)
    )
    _persist_ui_settings_for_current_account()


def autosave_ui_settings_for_current_account():
    account = st.session_state.get("current_account")
    if not account:
        st.session_state["persisted_ui_settings_snapshot"] = None
        return
    current_settings = _current_ui_settings_from_session()
    persisted_snapshot = st.session_state.get("persisted_ui_settings_snapshot")
    if persisted_snapshot == current_settings:
        return
    if set_account_settings(account, current_settings):
        st.session_state["persisted_ui_settings_snapshot"] = current_settings


def sync_ui_settings_for_active_account():
    current_account = st.session_state.get("current_account")
    loaded_for_account = st.session_state.get("settings_loaded_for_account")

    # Skip reload only when account is unchanged and current settings still match
    # the last persisted snapshot. This prevents widget-key resets from being
    # written back as new settings when those widgets are not rendered.
    if loaded_for_account == current_account and current_account is not None:
        persisted_snapshot = st.session_state.get("persisted_ui_settings_snapshot")
        if isinstance(persisted_snapshot, dict) and _current_ui_settings_from_session() == persisted_snapshot:
            return

    if current_account is None:
        _apply_ui_settings_to_session(_default_ui_settings())
        _sync_settings_controls_from_session()
        st.session_state["settings_loaded_for_account"] = None
        st.session_state["persisted_ui_settings_snapshot"] = None
        return

    saved_settings = get_account_settings(current_account)
    if saved_settings is None:
        _apply_ui_settings_to_session(_default_ui_settings())
    else:
        _apply_ui_settings_to_session(saved_settings)
    _sync_settings_controls_from_session()
    st.session_state["persisted_ui_settings_snapshot"] = _current_ui_settings_from_session()
    st.session_state["settings_loaded_for_account"] = current_account


def compute_win_probability(remaining_numbers, guesses_left):
    if remaining_numbers <= 0 or guesses_left <= 0:
        return 0.0
    return min(1.0, guesses_left / remaining_numbers)


def _fragment_or_passthrough(func):
    fragment_decorator = getattr(st, "fragment", None)
    if callable(fragment_decorator):
        return fragment_decorator(func)
    return func


def _fast_rerun(force=False):
    should_force = bool(force) or st.session_state.get("active_action") == "Blackjack"
    if not should_force:
        return
    rerun_func = getattr(st, "rerun", None)
    if not callable(rerun_func):
        return
    try:
        rerun_func(scope="fragment")
    except Exception:
        rerun_func()


def _svg_background_uri(svg: str) -> str:
    """Return a data URI for an SVG string (base64-encoded).

    This is a lightweight helper used by the theming code to embed
    small SVG images as CSS backgrounds.
    """
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def apply_theme():
    dark_mode_enabled = st.session_state.get("setting_dark_mode", True)
    animations_enabled = st.session_state.get("setting_enable_animations", True)
    active_action = st.session_state.get("active_action")
    compact_game_layout = active_action in {"Play game", "Blackjack"}
    block_max_width = "1240px" if compact_game_layout else "1100px"
    block_padding_top = "0.35rem" if compact_game_layout else "1.15rem"
    block_padding_bottom = "0.9rem" if compact_game_layout else "2.25rem"
    form_transition = (
        "transform 150ms ease, box-shadow 170ms ease, border-color 150ms ease" if animations_enabled else "none"
    )
    form_hover_transform = "translateY(-1px)" if animations_enabled else "none"
    input_transition = "border-color 140ms ease, box-shadow 140ms ease" if animations_enabled else "none"
    button_transition = (
        "transform 130ms ease, filter 130ms ease, box-shadow 160ms ease" if animations_enabled else "none"
    )
    button_hover_transform = "translateY(-1px)" if animations_enabled else "none"
    button_active_transform = "translateY(0)" if animations_enabled else "none"
    if dark_mode_enabled:
        background_layers = (
            "radial-gradient(900px 520px at -6% -10%, rgba(64, 128, 120, 0.12), transparent 40%),"
            "linear-gradient(180deg, rgba(6,10,12,0.55), rgba(10,16,18,0.6))"
        )
        sidebar_background = (
            "linear-gradient(180deg, rgba(10,16,18,0.6), rgba(8,12,14,0.5))"
        )
        text_color = "#e8f6f1"
        heading_color = "#dbeee7"
        card_background = "rgba(18,24,26,0.46)"  # translucent glass
        card_border = "rgba(255,255,255,0.06)"
        card_shadow = "0 8px 28px rgba(2,6,8,0.6), inset 0 1px 0 rgba(255,255,255,0.02)"
        input_background = "rgba(12,18,20,0.42)"
        input_text_color = "#eaf8f3"
        input_placeholder_color = "rgba(220, 237, 229, 0.52)"
        input_border = "rgba(255,255,255,0.06)"
        focus_border = "rgba(120, 200, 180, 0.9)"
        focus_shadow = "0 6px 18px rgba(67,178,142,0.12)"
        button_background = (
            "linear-gradient(135deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.02)),"
            "linear-gradient(180deg, rgba(120, 200, 180, 0.15), rgba(120, 200, 180, 0.08))"
        )
        button_border = "rgba(120, 200, 180, 0.5)"
        button_text = "#f0fff8"
        submit_background = "linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02))"
        submit_border = "rgba(255,255,255,0.12)"
        submit_text = "#04201a"
        header_background = "rgba(8,12,14,0.4)"
        sidebar_border = "rgba(255,255,255,0.04)"
        muted_label = "rgba(200,220,212,0.78)"
        divider = "rgba(255,255,255,0.04)"
        sidebar_select_background = "rgba(12,18,20,0.38)"
        sidebar_select_border = "rgba(255,255,255,0.04)"
        sidebar_select_hover_border = "rgba(120,200,180,0.85)"
        sidebar_select_shadow = "0 8px 20px rgba(4,8,10,0.5)"
        sidebar_select_label = "rgba(220,238,230,0.9)"
        avatar_nav_color = "#e7f8f2"
        header_title_color = "#ffd387"
        bj_label_color = "#ecfff9"
        bj_deck_color = "#d9f6ef"
        bj_deck_count_color = "rgba(237, 252, 247, 0.92)"
        bj_empty_slot_color = "rgba(241, 255, 250, 0.74)"
    else:
        background_layers = (
            "radial-gradient(900px 520px at -6% -10%, rgba(200, 240, 235, 0.25), transparent 40%),"
            "linear-gradient(180deg, rgba(255,255,255,0.62), rgba(245,249,248,0.7))"
        )
        sidebar_background = (
            "linear-gradient(180deg, rgba(255,255,255,0.66), rgba(245,249,248,0.6))"
        )
        text_color = "#07322b"
        heading_color = "#0b5a4f"
        card_background = "rgba(255,255,255,0.62)"  # translucent glass
        card_border = "rgba(255,255,255,0.6)"
        card_shadow = "0 8px 22px rgba(12,36,32,0.08), inset 0 1px 0 rgba(255,255,255,0.6)"
        input_background = "rgba(255,255,255,0.7)"
        input_text_color = "#08322a"
        input_placeholder_color = "rgba(10, 60, 50, 0.38)"
        input_border = "rgba(12,88,74,0.08)"
        focus_border = "rgba(30,150,120,0.9)"
        focus_shadow = "0 6px 16px rgba(34,160,130,0.08)"
        button_background = (
            "linear-gradient(180deg, rgba(119, 205, 178, 0.32), rgba(119, 205, 178, 0.28)),"
            "linear-gradient(180deg, rgba(10, 80, 70, 0.48), rgba(10, 80, 70, 0.42))"
        )
        button_border = "rgba(80, 170, 150, 0.4)"
        button_text = "#042a22"
        submit_background = "linear-gradient(180deg, rgba(16,120,96,0.9), rgba(70,170,140,0.9))"
        submit_border = "rgba(30,150,120,0.14)"
        submit_text = "#ffffff"
        header_background = "rgba(255,255,255,0.65)"
        sidebar_border = "rgba(10,80,68,0.04)"
        muted_label = "rgba(6,40,34,0.7)"
        divider = "rgba(10,80,68,0.06)"
        sidebar_select_background = "rgba(255,255,255,0.72)"
        sidebar_select_border = "rgba(10,80,68,0.06)"
        sidebar_select_hover_border = "rgba(30,150,120,0.85)"
        sidebar_select_shadow = "0 8px 18px rgba(12,36,32,0.06)"
        sidebar_select_label = "rgba(6,40,34,0.9)"
        avatar_nav_color = "#0b5a4f"
        header_title_color = "#b8860a"
        bj_label_color = "#0b5a4f"
        bj_deck_color = "#08322a"
        bj_deck_count_color = "rgba(6, 40, 34, 0.92)"
        bj_empty_slot_color = "rgba(6, 40, 34, 0.88)"

    home_button_images = {
        "home_card_play_game": _svg_background_uri(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 420 220'>"
            "<rect width='420' height='220' fill='none'/>"
            "<circle cx='210' cy='112' r='82' fill='none' stroke='white' stroke-opacity='0.27' stroke-width='10'/>"
            "<circle cx='210' cy='112' r='54' fill='none' stroke='white' stroke-opacity='0.33' stroke-width='9'/>"
            "<circle cx='210' cy='112' r='26' fill='none' stroke='white' stroke-opacity='0.38' stroke-width='8'/>"
            "<text x='210' y='124' text-anchor='middle' font-size='42' font-weight='700' fill='white' fill-opacity='0.52'>#?</text>"
            "</svg>"
        ),
        "home_card_blackjack": _svg_background_uri(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 420 220'>"
            "<rect width='420' height='220' fill='none'/>"
            "<rect x='90' y='58' width='108' height='134' rx='14' fill='white' fill-opacity='0.19' stroke='white' stroke-opacity='0.35'/>"
            "<rect x='200' y='34' width='126' height='148' rx='16' fill='white' fill-opacity='0.24' stroke='white' stroke-opacity='0.4'/>"
            "<text x='232' y='90' font-size='34' font-weight='700' fill='white' fill-opacity='0.55'>A</text>"
            "<text x='256' y='146' font-size='56' font-weight='700' fill='white' fill-opacity='0.55'>♠</text>"
            "</svg>"
        ),
        "home_card_leaderboards": _svg_background_uri(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 420 220'>"
            "<rect width='420' height='220' fill='none'/>"
            "<rect x='98' y='122' width='54' height='70' rx='10' fill='white' fill-opacity='0.27'/>"
            "<rect x='176' y='88' width='62' height='104' rx='10' fill='white' fill-opacity='0.35'/>"
            "<rect x='262' y='58' width='60' height='134' rx='10' fill='white' fill-opacity='0.3'/>"
            "<circle cx='292' cy='42' r='18' fill='white' fill-opacity='0.34'/>"
            "<path d='M292 24 L297 37 H311 L299 45 L304 58 L292 50 L280 58 L285 45 L273 37 H287 Z' fill='white' fill-opacity='0.54'/>"
            "</svg>"
        ),
        "home_card_add_withdraw": _svg_background_uri(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 420 220'>"
            "<rect width='420' height='220' fill='none'/>"
            "<rect x='72' y='52' width='278' height='116' rx='18' fill='white' fill-opacity='0.2' stroke='white' stroke-opacity='0.34'/>"
            "<text x='209' y='128' text-anchor='middle' font-size='62' font-weight='700' fill='white' fill-opacity='0.5'>$</text>"
            "<path d='M88 92 H142 M128 78 L144 92 L128 106' stroke='white' stroke-opacity='0.56' stroke-width='8' stroke-linecap='round' stroke-linejoin='round'/>"
            "<path d='M332 128 H276 M290 114 L274 128 L290 142' stroke='white' stroke-opacity='0.56' stroke-width='8' stroke-linecap='round' stroke-linejoin='round'/>"
            "</svg>"
        ),
        "home_card_lookup": _svg_background_uri(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 420 220'>"
            "<rect width='420' height='220' fill='none'/>"
            "<circle cx='164' cy='108' r='44' fill='none' stroke='white' stroke-opacity='0.47' stroke-width='12'/>"
            "<path d='M194 138 L238 182' stroke='white' stroke-opacity='0.53' stroke-width='12' stroke-linecap='round'/>"
            "<rect x='240' y='58' width='108' height='104' rx='14' fill='white' fill-opacity='0.21' stroke='white' stroke-opacity='0.32'/>"
            "<circle cx='276' cy='90' r='14' fill='white' fill-opacity='0.42'/>"
            "<rect x='258' y='116' width='56' height='10' rx='5' fill='white' fill-opacity='0.38'/>"
            "<rect x='258' y='132' width='46' height='10' rx='5' fill='white' fill-opacity='0.32'/>"
            "</svg>"
        ),
        "home_card_calc_odds": _svg_background_uri(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 420 220'>"
            "<rect width='420' height='220' fill='none'/>"
            "<path d='M82 160 L152 104 L216 124 L304 62' fill='none' stroke='white' stroke-opacity='0.56' stroke-width='10' stroke-linecap='round' stroke-linejoin='round'/>"
            "<circle cx='304' cy='62' r='11' fill='white' fill-opacity='0.48'/>"
            "<rect x='74' y='74' width='82' height='96' rx='14' fill='white' fill-opacity='0.22' stroke='white' stroke-opacity='0.34'/>"
            "<rect x='92' y='96' width='46' height='10' rx='5' fill='white' fill-opacity='0.44'/>"
            "<rect x='92' y='114' width='46' height='10' rx='5' fill='white' fill-opacity='0.38'/>"
            "<rect x='92' y='132' width='34' height='10' rx='5' fill='white' fill-opacity='0.32'/>"
            "</svg>"
        ),
        "home_card_admin_odds": _svg_background_uri(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 420 220'>"
            "<rect width='420' height='220' fill='none'/>"
            "<circle cx='208' cy='110' r='52' fill='none' stroke='white' stroke-opacity='0.34' stroke-width='10'/>"
            "<circle cx='208' cy='110' r='20' fill='none' stroke='white' stroke-opacity='0.48' stroke-width='10'/>"
            "<path d='M208 44 V64 M208 156 V176 M142 110 H162 M254 110 H274' stroke='white' stroke-opacity='0.52' stroke-width='10' stroke-linecap='round'/>"
            "<path d='M154 62 L168 76 M248 144 L262 158 M154 158 L168 144 M248 76 L262 62' stroke='white' stroke-opacity='0.4' stroke-width='8' stroke-linecap='round'/>"
            "</svg>"
        ),
        "home_card_admin_accounts": _svg_background_uri(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 420 220'>"
            "<rect width='420' height='220' fill='none'/>"
            "<circle cx='148' cy='92' r='24' fill='white' fill-opacity='0.4'/>"
            "<path d='M106 156 C114 128 182 128 190 156' fill='none' stroke='white' stroke-opacity='0.46' stroke-width='12' stroke-linecap='round'/>"
            "<circle cx='258' cy='86' r='20' fill='white' fill-opacity='0.32'/>"
            "<path d='M226 148 C234 124 282 124 290 148' fill='none' stroke='white' stroke-opacity='0.38' stroke-width='10' stroke-linecap='round'/>"
            "<rect x='304' y='94' width='34' height='16' rx='5' fill='white' fill-opacity='0.46'/>"
            "</svg>"
        ),
        "home_card_admin_game_limits": _svg_background_uri(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 420 220'>"
            "<rect width='420' height='220' fill='none'/>"
            "<rect x='100' y='68' width='114' height='84' rx='12' fill='white' fill-opacity='0.24' stroke='white' stroke-opacity='0.38'/>"
            "<rect x='120' y='88' width='30' height='16' fill='white' fill-opacity='0.52'/>"
            "<rect x='165' y='88' width='30' height='16' fill='white' fill-opacity='0.42'/>"
            "<rect x='120' y='116' width='75' height='16' rx='4' fill='white' fill-opacity='0.26'/>"
            "<path d='M240 100 L295 100 M240 130 L295 130 M240 160 L295 160' stroke='white' stroke-opacity='0.45' stroke-width='8' stroke-linecap='round'/>"
            "<circle cx='315' cy='130' r='16' fill='white' fill-opacity='0.35'/>"
            "</svg>"
        ),
    }
    home_button_selector_list = ",\n        ".join(
        f"div.st-key-{card_key} div.stButton > button" for card_key in home_button_images
    )
    home_button_text_selector_list = ",\n        ".join(
        f"div.st-key-{card_key} div.stButton > button p" for card_key in home_button_images
    )
    home_button_background_css = "\n        ".join(
        f"div.st-key-{card_key} div.stButton > button {{"
        f"background-image: linear-gradient(135deg, rgba(2, 12, 10, 0.22) 8%, rgba(2, 12, 10, 0.52) 100%), {image_uri};"
        "background-size: cover;"
        "background-position: center;"
        "background-repeat: no-repeat;"
        "}}"
        for card_key, image_uri in home_button_images.items()
    )

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;700;800&family=Space+Grotesk:wght@500;700&display=swap');

        [data-testid="stHeaderActionElements"] {{
            display: none !important;
        }}

        .stApp {{
            background: {background_layers};
            color: {text_color};
            font-family: "Manrope", "Avenir Next", "Segoe UI", sans-serif;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            -webkit-backdrop-filter: blur(10px) saturate(150%);
            backdrop-filter: blur(10px) saturate(150%);
        }}

        /* Ensure readable text color across many components (useful for light theme contrast) */
        .stApp, .stApp p, .stApp label, .stApp a, .stMarkdownContainer, [data-testid="stMarkdownContainer"],
        .block-container, .stText, .stCaptionContainer, [data-testid="stMetric"] {{
            color: {text_color} !important;
        }}

        [data-testid="stHeader"] {{
            display: none !important;
        }}

        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapseButton"],
        button[aria-label="Close sidebar"],
        button[aria-label="Open sidebar"] {{
            display: none !important;
        }}

        .block-container {{
            max-width: {block_max_width};
            padding-top: {block_padding_top};
            padding-bottom: {block_padding_bottom};
        }}

        h1, h2, h3 {{
            font-family: "Space Grotesk", "Avenir Next Condensed", sans-serif !important;
            letter-spacing: 0.01em;
            color: {heading_color} !important;
        }}

        p, label, [data-testid="stCaptionContainer"], [data-testid="stMarkdownContainer"] {{
            color: {muted_label} !important;
        }}

        [data-testid="stSidebar"] {{
            background: {sidebar_background};
            border-right: 1px solid {sidebar_border};
            backdrop-filter: blur(8px);
            position: relative !important;
            z-index: 10 !important;
        }}

        [data-testid="stForm"] {{
            border-radius: 18px;
            border: 1px solid {card_border};
            background: {card_background};
            box-shadow: {card_shadow}, inset 0 0.5px 0.5px rgba(255,255,255,0.08);
            padding: 0.95rem 1rem 0.75rem 1rem;
            transition: {form_transition};
            -webkit-backdrop-filter: blur(12px) saturate(160%);
            backdrop-filter: blur(12px) saturate(160%);
            background-image: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.004));
            border-radius: 18px;
            border-top: 1px solid rgba(255,255,255,0.14);
            border-left: 1px solid rgba(255,255,255,0.10);
        }}

        [data-testid="stForm"]:hover {{
            transform: {form_hover_transform};
            box-shadow: 0 22px 42px rgba(0, 0, 0, 0.18);
        }}

        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        [data-baseweb="textarea"] > div {{
            border-radius: 12px !important;
            background: {input_background} !important;
            border-color: {input_border} !important;
            border-top: 1px solid rgba(255,255,255,0.12) !important;
            border-left: 1px solid rgba(255,255,255,0.08) !important;
            box-shadow: inset 0 0.5px 0.5px rgba(255,255,255,0.05) !important;
            transition: {input_transition};
        }}

        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea,
        [data-baseweb="select"] input {{
            color: {input_text_color} !important;
            -webkit-text-fill-color: {input_text_color} !important;
            font-weight: 600;
        }}

        [data-baseweb="input"] input::placeholder,
        [data-baseweb="textarea"] textarea::placeholder {{
            color: {input_placeholder_color} !important;
            -webkit-text-fill-color: {input_placeholder_color} !important;
        }}

        [data-baseweb="input"] > div:focus-within,
        [data-baseweb="select"] > div:focus-within,
        [data-baseweb="textarea"] > div:focus-within,
        [data-baseweb="input"] > div[aria-invalid="true"],
        [data-baseweb="textarea"] > div[aria-invalid="true"],
        [data-baseweb="select"] > div[aria-invalid="true"] {{
            border-color: {focus_border} !important;
            box-shadow: {focus_shadow} !important;
        }}

        div.stButton > button,
        div.stDownloadButton > button {{
            min-height: 2.6rem;
            border-radius: 12px;
            border: 1px solid {button_border};
            background: {button_background};
            color: {button_text};
            font-family: "Space Grotesk", "Avenir Next Condensed", sans-serif;
            font-size: 0.96rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            box-shadow: 0 10px 28px rgba(4, 8, 10, 0.48), inset 0 1px 0 rgba(255,255,255,0.04);
            transition: {button_transition};
            backdrop-filter: blur(6px) saturate(130%);
        }}

        div.stFormSubmitButton > button {{
            min-height: 2.8rem;
            border-radius: 14px;
            border: 1px solid {submit_border};
            background: {submit_background};
            color: {submit_text};
            font-family: "Space Grotesk", "Avenir Next Condensed", sans-serif;
            font-size: 0.99rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            box-shadow: 0 10px 22px rgba(0, 0, 0, 0.16);
            transition: {button_transition};
        }}

        div.stButton > button p,
        div.stFormSubmitButton > button p {{
            color: inherit !important;
            font-weight: inherit !important;
            margin: 0 !important;
            line-height: 1 !important;
            padding: 0 !important;
        }}

        div.stButton > button:hover:enabled,
        div.stFormSubmitButton > button:hover:enabled {{
            transform: {button_hover_transform};
            filter: brightness(1.04);
            box-shadow: 0 16px 30px rgba(0, 0, 0, 0.2);
        }}

        div.stButton > button:active:enabled,
        div.stFormSubmitButton > button:active:enabled {{
            transform: {button_active_transform};
        }}

        div.stButton > button:disabled,
        div.stFormSubmitButton > button:disabled {{
            opacity: 0.46;
            cursor: not-allowed;
        }}

        [data-testid="stAlert"] {{
            border-radius: 14px;
            border: 1px solid {card_border};
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.12), inset 0 0.5px 0.5px rgba(255,255,255,0.06);
            border-top: 1px solid rgba(255,255,255,0.12);
            border-left: 1px solid rgba(255,255,255,0.10);
        }}

        [data-testid="stMarkdownContainer"] hr {{
            border-top: 1px solid {divider};
        }}

        [data-testid="stDataFrame"],
        [data-testid="stTable"] {{
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.06);
            box-shadow: 0 8px 20px rgba(0,0,0,0.1), inset 0 0.5px 0 rgba(255,255,255,0.05);
        }}

        [data-testid="stPopover"] > div > button {{
            min-height: 2.25rem;
            min-width: 2.25rem;
            width: 2.25rem;
            padding: 0;
            border-radius: 999px;
            border: 2px solid {button_border};
            background: {button_background};
            color: {button_text};
            font-family: "Space Grotesk", "Avenir Next Condensed", sans-serif;
            font-weight: 700;
            letter-spacing: 0.01em;
            font-size: 1.15rem;
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.16);
            backdrop-filter: blur(6px) saturate(130%);
            display: flex;
            align-items: center;
            justify-content: center;
            line-height: 1;
        }}

        [data-testid="stPopover"] > div > button::after {{
            content: none !important;
            display: none !important;
        }}

        [data-testid="stPopover"] > div > button:hover {{
            filter: brightness(1.03);
            transform: {button_hover_transform};
        }}

        [data-testid="stPopover"] [data-baseweb="checkbox"] {{
            transform: scale(0.92);
            transform-origin: left center;
        }}

        /* Popover content styling for both light and dark modes */
        [role="dialog"] {{
            background: {header_background} !important;
            border: 1px solid {card_border} !important;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.24) !important;
        }}

        [role="dialog"] * {{
            color: {text_color} !important;
        }}

        [role="dialog"] h4,
        [role="dialog"] h3,
        [role="dialog"] h2 {{
            color: {heading_color} !important;
        }}

        [role="dialog"] p,
        [role="dialog"] label,
        [role="dialog"] .stCaption {{
            color: {muted_label} !important;
        }}

        [role="dialog"] [data-testid="stMarkdownContainer"] {{
            color: {text_color} !important;
        }}

        [role="dialog"] [data-testid="stToggle"] {{
            color: {text_color} !important;
        }}

        [role="dialog"] [data-baseweb="checkbox"] label {{
            color: {muted_label} !important;
        }}

        /* Additional popover modal selectors for Streamlit variants */
        [data-baseweb="modal"] {{
            background: {header_background} !important;
        }}

        [data-baseweb="modal"] * {{
            color: {text_color} !important;
        }}

        /* Popover inner content */
        [data-testid="stPopover"] [data-testid="stForm"],
        [data-testid="stPopover"] > div:last-child {{
            background: {header_background} !important;
            color: {text_color} !important;
        }}

        [data-testid="stPopover"] [data-testid="stMarkdownContainer"] {{
            color: {text_color} !important;
        }}

        [data-testid="stPopover"] [data-testid="stCaptionContainer"] {{
            color: {muted_label} !important;
        }}

        [data-testid="stPopover"] [data-testid="stToggle"] [role="checkbox"] {{
            background: {input_background} !important;
        }}

        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] label {{
            color: inherit !important;
        }}

        [data-testid="stSidebar"] [data-testid="stSelectbox"] label {{
            margin-bottom: 0.32rem;
        }}

        [data-testid="stSidebar"] [data-testid="stSelectbox"] label p {{
            font-family: "Space Grotesk", "Avenir Next Condensed", sans-serif !important;
            font-size: 0.75rem !important;
            font-weight: 700 !important;
            letter-spacing: 0.065em;
            text-transform: uppercase;
            color: {sidebar_select_label} !important;
        }}

        [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div {{
            min-height: 2.78rem;
            border-radius: 14px !important;
            background: {sidebar_select_background} !important;
            border: 1px solid {sidebar_select_border} !important;
            box-shadow: {sidebar_select_shadow};
            transition: border-color 140ms ease, box-shadow 160ms ease, transform 120ms ease;
        }}

        [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover {{
            border-color: {sidebar_select_hover_border} !important;
            box-shadow: 0 16px 28px rgba(0, 0, 0, 0.18);
            transform: translateY(-1px);
        }}

        [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] input {{
            font-family: "Manrope", "Avenir Next", "Segoe UI", sans-serif !important;
            font-size: 0.97rem !important;
            font-weight: 700 !important;
            caret-color: transparent !important;
        }}

        [data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] [aria-hidden="true"] {{
            color: {input_text_color} !important;
            font-family: "Manrope", "Avenir Next", "Segoe UI", sans-serif !important;
            font-weight: 700 !important;
        }}

        {home_button_selector_list} {{
            min-height: 5.2rem;
            justify-content: flex-start;
            align-items: center;
            text-align: left;
            padding: 0.6rem 0.9rem;
            border-radius: 14px;
            overflow: hidden;
            backdrop-filter: blur(8px) saturate(140%);
            background: {button_background};
            border: 1px solid {button_border};
            box-shadow: 0 12px 32px rgba(2,6,8,0.44), inset 0 1px 0.5px rgba(255,255,255,0.04);
        }}

        {home_button_text_selector_list} {{
            text-shadow: 0 1px 2px rgba(0, 0, 0, 0.42);
        }}

        {home_button_background_css}

        div.st-key-top_sign_in_create div.stButton > button {{
            background: {button_background} !important;
            border: 1px solid {button_border} !important;
            color: {button_text} !important;
            box-shadow: 0 10px 28px rgba(4, 8, 10, 0.48), inset 0 1px 0 rgba(255,255,255,0.04) !important;
            backdrop-filter: blur(6px) saturate(130%) !important;
        }}

        /* Responsive design for smaller screens */
        @media (max-width: 1024px) {{
            [data-testid="stSidebar"] {{
                width: 280px !important;
                min-width: 280px !important;
                max-width: 280px !important;
            }}

            .block-container {{
                max-width: calc(100% - 300px) !important;
            }}
        }}

        @media (max-width: 768px) {{
            [data-testid="stSidebar"] {{
                width: 240px !important;
                min-width: 240px !important;
                max-width: 240px !important;
            }}

            .block-container {{
                max-width: calc(100% - 260px) !important;
            }}

            [data-testid="stSidebar"] [data-testid="stSelectbox"] {{
                margin-bottom: 0.75rem;
            }}

            {home_button_selector_list} {{
                min-height: 4rem;
                padding: 0.6rem 0.7rem;
            }}

            h2 {{
                font-size: 1.3rem !important;
            }}

            [data-testid="stSidebar"] h3 {{
                font-size: 0.9rem !important;
            }}
        }}

        @media (max-width: 600px) {{
            [data-testid="stSidebar"] {{
                width: 200px !important;
                min-width: 200px !important;
                max-width: 200px !important;
                font-size: 0.85rem;
                padding: 0.5rem !important;
            }}

            .block-container {{
                max-width: calc(100% - 220px) !important;
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
                padding-top: {block_padding_top} !important;
                padding-bottom: {block_padding_bottom} !important;
            }}

            [data-testid="stSidebar"] h3 {{
                font-size: 0.8rem;
                margin-bottom: 0.4rem;
            }}

            [data-testid="stMetric"] {{
                padding: 0.3rem 0 !important;
            }}

            [data-testid="stSidebar"] [data-testid="stSelectbox"] {{
                margin-bottom: 0.5rem;
            }}

            {home_button_selector_list} {{
                min-height: auto;
                padding: 0.5rem 0.6rem;
                font-size: 0.9rem;
            }}
        }}

        @media (min-width: 1025px) {{
            [data-testid="stSidebar"] {{
                width: 300px !important;
                min-width: 300px !important;
                max-width: 300px !important;
            }}

            .block-container {{
                max-width: {block_max_width} !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    
    # Store theme colors in session state for use by other rendering functions
    st.session_state["theme_avatar_nav_color"] = avatar_nav_color
    st.session_state["theme_header_title_color"] = header_title_color
    st.session_state["theme_bj_label_color"] = bj_label_color
    st.session_state["theme_bj_deck_color"] = bj_deck_color
    st.session_state["theme_bj_deck_count_color"] = bj_deck_count_color
    st.session_state["theme_bj_empty_slot_color"] = bj_empty_slot_color


def init_state():
    global _logout_server_started
    if not _logout_server_started:
        try:
            start_logout_server()
            _logout_server_started = True
        except Exception:
            # Server might already be running or port in use; continue anyway
            pass
    
    st.session_state.setdefault("current_account", None)
    st.session_state.setdefault("client_session_id", uuid.uuid4().hex)
    st.session_state.setdefault("account_session_notice", None)
    st.session_state.setdefault("storage_unavailable", False)
    st.session_state.setdefault("storage_unavailable_message", "")
    try:
        loaded_odds = load_saved_odds()
        st.session_state["storage_unavailable"] = False
        st.session_state["storage_unavailable_message"] = ""
    except Exception as exc:
        loaded_odds = st.session_state.get("odds", 1.5)
        st.session_state["storage_unavailable"] = True
        st.session_state["storage_unavailable_message"] = str(exc)
    st.session_state.setdefault("odds", loaded_odds)
    st.session_state.setdefault("active_action", "Home")
    st.session_state.setdefault("redirect_to_home", False)
    st.session_state.setdefault("show_auth_flow", False)
    st.session_state.setdefault("auth_flow_mode", None)
    st.session_state.setdefault("pending_new_account", None)
    st.session_state.setdefault("player_guess_round", None)
    st.session_state.setdefault("computer_guess_round", None)
    st.session_state.setdefault("computer_guess_in_progress", False)
    st.session_state.setdefault("selected_game_mode", None)
    st.session_state.setdefault("sidebar_prob_display", None)
    st.session_state.setdefault("sidebar_prob_history_len", 0)
    st.session_state.setdefault("player_guess_input_text", "")
    st.session_state.setdefault("guest_mode_active", False)
    st.session_state.setdefault("guest_mode_setup", False)
    st.session_state.setdefault("blackjack_guest_mode_setup", False)
    st.session_state.setdefault("guest_balance", 0.0)
    st.session_state.setdefault("guest_completion_message", None)
    st.session_state.setdefault("blackjack_round", None)
    st.session_state.setdefault("blackjack_lan_spectate_table_id", None)
    st.session_state.setdefault("blackjack_lan_spectate_password", "")
    st.session_state.setdefault("blackjack_multiplayer_guest_account", None)
    st.session_state.setdefault("blackjack_multiplayer_guest_setup", False)
    st.session_state.setdefault("blackjack_pending_bet", None)
    st.session_state.setdefault("blackjack_pending_replay_bet", None)
    st.session_state.setdefault("blackjack_guest_total_net", 0.0)
    st.session_state.setdefault("setting_allow_negative_balance", False)
    st.session_state.setdefault("setting_dark_mode", True)
    st.session_state.setdefault("setting_enable_animations", True)
    st.session_state.setdefault("setting_confirm_before_bet", True)
    st.session_state.setdefault("setting_profile_avatar", "")
    st.session_state.setdefault("settings_control_allow_negative_balance", False)
    st.session_state.setdefault("settings_control_dark_mode", True)
    st.session_state.setdefault("settings_control_enable_animations", True)
    st.session_state.setdefault("settings_control_confirm_before_bet", True)
    st.session_state.setdefault("settings_loaded_for_account", None)
    st.session_state.setdefault("persisted_ui_settings_snapshot", None)
    st.session_state.setdefault("pending_force_sign_in_account", None)


def _current_session_id():
    session_id = st.session_state.get("client_session_id")
    if isinstance(session_id, str) and session_id.strip():
        return session_id.strip()
    generated = uuid.uuid4().hex
    st.session_state["client_session_id"] = generated
    return generated


def _sign_out_current_account(session_notice=None):
    account = st.session_state.get("current_account")
    if account:
        try:
            auto_remove_blackjack_lan_player(account)
        except Exception:
            pass
        try:
            release_account_session(account, _current_session_id())
        except Exception:
            pass

    st.session_state["current_account"] = None
    st.session_state["client_session_id"] = None
    st.session_state["show_auth_flow"] = False
    st.session_state["auth_flow_mode"] = None
    st.session_state["pending_new_account"] = None
    st.session_state["active_action"] = "Home"
    st.session_state["redirect_to_home"] = False
    st.session_state["settings_loaded_for_account"] = None
    st.session_state["persisted_ui_settings_snapshot"] = None
    st.session_state["pending_force_sign_in_account"] = None
    st.session_state["blackjack_lan_spectate_table_id"] = None
    st.session_state["blackjack_lan_spectate_password"] = ""
    end_guest_session(set_completion_message=False)
    if session_notice:
        st.session_state["account_session_notice"] = session_notice


def _enforce_account_session_ownership():
    account = st.session_state.get("current_account")
    if account is None:
        return
    try:
        acquired, reason = acquire_account_session(account, _current_session_id())
    except Exception:
        _sign_out_current_account(
            session_notice="Account storage is temporarily unavailable. You were signed out. Guest mode is still available."
        )
        return
    if acquired:
        return
    if reason == "in_use":
        notice = f"'{account}' is already active in another session. You were signed out."
    elif reason == "account_not_found":
        notice = f"'{account}' no longer exists. You were signed out."
    else:
        notice = f"Could not validate your session for '{account}'. Please sign in again."
    _sign_out_current_account(session_notice=notice)


def _render_account_session_notice():
    notice = st.session_state.get("account_session_notice")
    if not notice:
        return
    st.warning(notice)
    st.session_state["account_session_notice"] = None


def _render_storage_unavailable_notice():
    if not st.session_state.get("storage_unavailable", False):
        return
    st.warning(
        "Account storage is temporarily unavailable. Sign-in and saved accounts are disabled right now, "
        "but Guest mode still works."
    )


def _auto_remove_lan_player_when_not_in_blackjack():
    current_account = st.session_state.get("current_account")
    guest_multiplayer_account = st.session_state.get("blackjack_multiplayer_guest_account")
    active_player = current_account or guest_multiplayer_account
    if not active_player:
        return
    if st.session_state.get("active_action") == "Blackjack" and not st.session_state.get("show_auth_flow", False):
        return
    joined_table = find_blackjack_lan_table_for_player(active_player)
    if joined_table is None:
        return
    auto_remove_blackjack_lan_player(active_player)


def _clear_blackjack_multiplayer_guest_account(delete_record=True):
    guest_account = st.session_state.get("blackjack_multiplayer_guest_account")
    if not guest_account:
        st.session_state["blackjack_multiplayer_guest_setup"] = False
        return
    try:
        auto_remove_blackjack_lan_player(guest_account)
    except Exception:
        pass
    try:
        release_account_session(guest_account, _current_session_id())
    except Exception:
        pass
    if delete_record:
        try:
            delete_account(guest_account)
        except Exception:
            pass
    st.session_state["blackjack_multiplayer_guest_account"] = None
    st.session_state["blackjack_multiplayer_guest_setup"] = False


def current_balance():
    account = st.session_state["current_account"]
    if account is None:
        if st.session_state.get("guest_mode_active", False):
            return float(st.session_state.get("guest_balance", 0.0))
        return None
    return get_account_value(account)


def end_guest_session(set_completion_message=False):
    if set_completion_message and st.session_state.get("guest_mode_active", False):
        final_guest_balance = float(st.session_state.get("guest_balance", 0.0))
        st.session_state["guest_completion_message"] = (
            f"You have ${format_money(final_guest_balance)}."
        )
    st.session_state["guest_mode_active"] = False
    st.session_state["guest_mode_setup"] = False
    st.session_state["blackjack_guest_mode_setup"] = False
    st.session_state["guest_balance"] = 0.0
    st.session_state["selected_game_mode"] = None
    st.session_state["player_guess_round"] = None
    st.session_state["computer_guess_round"] = None
    st.session_state["computer_guess_in_progress"] = False
    st.session_state["blackjack_round"] = None
    st.session_state["blackjack_pending_bet"] = None
    st.session_state["blackjack_pending_replay_bet"] = None
    st.session_state["blackjack_guest_total_net"] = 0.0
    _clear_blackjack_multiplayer_guest_account(delete_record=True)


def is_debt_allowed():
    return bool(st.session_state.get("setting_allow_negative_balance", False))


def can_afford_account_charge(account, charge_amount):
    if is_debt_allowed():
        return True
    balance = get_account_value(account)
    if balance is None:
        return False
    return float(balance) >= float(charge_amount)


def is_bet_confirmation_enabled():
    return bool(st.session_state.get("setting_confirm_before_bet", True))


def show_win_confetti():
    if st.session_state.get("setting_enable_animations", True):
        components.html(
            """
            <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.3/dist/confetti.browser.min.js"></script>
            <script>
            (function () {
              const duration = 1500;
              const end = Date.now() + duration;
              (function frame() {
                confetti({
                  particleCount: 5,
                  startVelocity: 45,
                  spread: 70,
                  gravity: 1.1,
                  ticks: 220,
                  origin: { x: Math.random(), y: 0 }
                });
                if (Date.now() < end) {
                  requestAnimationFrame(frame);
                }
              })();
            })();
            </script>
            """,
            height=0,
            width=0,
        )


def is_admin_user():
    current_account = st.session_state.get("current_account")
    if current_account is None:
        return False
    if current_account == ADMIN_ACCOUNT_NAME:
        return True
    try:
        return bool(get_account_admin_status(current_account))
    except Exception:
        return False


def can_create_admins():
    return st.session_state.get("current_account") == ADMIN_ACCOUNT_NAME


def render_header():
    header_title_color = st.session_state.get("theme_header_title_color", "#ffd387")
    st.markdown(
        f"""
        <div style="
            margin: 0 0 0.55rem 0;
            text-align: center;
            font-size: clamp(2.2rem, 5.8vw, 3.7rem);
            font-weight: 800;
            letter-spacing: 0.11em;
            text-transform: uppercase;
            color: {header_title_color};
            text-shadow:
                0 0 12px rgba(255, 211, 135, 0.38),
                0 14px 28px rgba(0, 0, 0, 0.22);
            font-family: 'Space Grotesk', 'Avenir Next Condensed', sans-serif;
        ">GAMBLY</div>
        """,
        unsafe_allow_html=True,
    )


def render_top_controls():
    current_account = st.session_state.get("current_account")
    active_action = st.session_state.get("active_action")
    show_auth_flow = st.session_state.get("show_auth_flow", False)

    st.markdown(
        """
        <div style="
            display: flex;
            align-items: center;
            justify-content: flex-start;
            margin: 0 0 0.65rem 0;
        "></div>
        """,
        unsafe_allow_html=True,
    )
    # Show user icon only on home page
    if current_account and active_action == "Home" and not show_auth_flow:
        _sync_settings_controls_from_session()
        avatar_col, _spacer = st.columns([1.2, 4.99])
        with avatar_col:
            with st.popover(_profile_avatar_trigger_text(current_account), use_container_width=False):
                st.markdown("#### Settings")
                st.caption(f"Signed in as {current_account}")
                st.caption(f"Avatar: {_profile_avatar_display_text(current_account)}")
                st.toggle(
                    "Allow negative balance",
                    key="settings_control_allow_negative_balance",
                    on_change=_persist_ui_settings_from_controls,
                )
                st.toggle(
                    "Dark mode",
                    key="settings_control_dark_mode",
                    on_change=_persist_ui_settings_from_controls,
                )
                st.toggle(
                    "Enable animations",
                    key="settings_control_enable_animations",
                    on_change=_persist_ui_settings_from_controls,
                )
                st.toggle(
                    "Confirm before placing bet",
                    key="settings_control_confirm_before_bet",
                    on_change=_persist_ui_settings_from_controls,
                )
                st.markdown("---")
                if st.button(
                    "Change profile picture",
                    key="profile_change_profile_picture",
                    use_container_width=True,
                ):
                    st.session_state["show_auth_flow"] = False
                    st.session_state["auth_flow_mode"] = None
                    st.session_state["pending_new_account"] = None
                    st.session_state["active_action"] = "Change profile picture"
                    _fast_rerun()
                if st.button("Change password", key="profile_change_password", use_container_width=True):
                    st.session_state["show_auth_flow"] = False
                    st.session_state["auth_flow_mode"] = None
                    st.session_state["pending_new_account"] = None
                    st.session_state["active_action"] = "Change password"
                    _fast_rerun()
                if st.button("Sign out", key="profile_sign_out", use_container_width=True):
                    _sign_out_current_account()
                    st.success("Signed out.")
                    _fast_rerun()
    elif not current_account:
        if active_action == "Home" and not show_auth_flow:
            sign_in_col, _spacer = st.columns([1.22, 4.97])
            with sign_in_col:
                sign_in_disabled = bool(st.session_state.get("storage_unavailable", False))
                if st.button(
                    "Sign in / Create Account",
                    key="top_sign_in_create",
                    use_container_width=True,
                    disabled=sign_in_disabled,
                ):
                    st.session_state["show_auth_flow"] = True
                    st.session_state["auth_flow_mode"] = None
                    st.session_state["pending_new_account"] = None
                    _fast_rerun()


def is_guessing_in_progress():
    player_round = st.session_state.get("player_guess_round")
    if player_round and player_round.get("status") == "active":
        return True
    blackjack_round = st.session_state.get("blackjack_round")
    if blackjack_round and blackjack_round.get("status") == "player_turn":
        return True
    return bool(st.session_state.get("computer_guess_in_progress", False))


def render_player_analytics_sidebar(round_state):
    if not round_state or round_state.get("status") != "active":
        return

    history = round_state.get("history", [])
    low = round_state["low"]
    high = round_state["high"]
    guesses_left = round_state["guesses_left"]
    remaining_numbers = max(0, high - low + 1)
    win_probability = compute_win_probability(remaining_numbers, guesses_left)
    attempts_used = round_state["starting_guesses"] - guesses_left

    with st.sidebar:
        st.markdown(f"### Payout: ${format_money(round_state['payout'])}")
        metric_placeholder = st.empty()
        st.metric("Attempts used", f"{attempts_used}/{round_state['starting_guesses']}")
        st.metric("Remaining range", f"{low} to {high}")

        if history:
            metric_placeholder.metric("Win probability", f"{win_probability * 100:.1f}%")
            st.session_state["sidebar_prob_display"] = win_probability
            st.session_state["sidebar_prob_history_len"] = len(history)
            with st.expander("Guess history"):
                for point in history:
                    if point["result"] == "start":
                        st.write(
                            f"Attempt {point['attempt']}: start | "
                            f"{point['win_probability'] * 100:.1f}% to win"
                        )
                    else:
                        st.write(
                            f"Attempt {point['attempt']}: guessed {point['guess']} ({point['result']}) | "
                            f"{point['win_probability'] * 100:.1f}% to win"
                        )


def render_computer_analytics_sidebar(round_state):
    if not round_state:
        return

    low = int(round_state.get("low", 1))
    high = int(round_state.get("high", 1))
    remaining_numbers = max(0, high - low + 1)
    attempts_used = int(round_state.get("attempts_used", 0))
    total_attempts = int(round_state.get("guesses", 1))
    history = round_state.get("history", [])

    if history:
        current_probability = float(history[-1].get("win_probability", 0.0))
    else:
        guesses_left = max(0, total_attempts - attempts_used)
        current_probability = compute_win_probability(remaining_numbers, guesses_left)

    with st.sidebar:
        st.markdown(f"### Payout: ${format_money(round_state['payout'])}")
        st.metric("Computer win probability", f"{current_probability * 100:.1f}%")
        st.metric("Attempts used", f"{attempts_used}/{total_attempts}")
        st.metric("Remaining range", f"{low} to {high}")
        with st.expander("Guess history"):
            if not history:
                st.write("No guesses yet.")
            else:
                for point in history:
                    if point.get("result") == "start":
                        st.write(
                            f"Attempt 0: start | "
                            f"{point.get('win_probability', 0.0) * 100:.1f}% to win"
                        )
                    else:
                        st.write(
                            f"Attempt {point['attempt']}: guessed {point['guess']} ({point['result']}) | "
                            f"{point.get('win_probability', 0.0) * 100:.1f}% to win"
                        )


def render_blackjack_analytics_sidebar(round_state, account, is_guest_mode):
    if not round_state:
        return

    player_cards = round_state.get("player_cards", [])
    dealer_cards = round_state.get("dealer_cards", [])
    player_total = blackjack_hand_total(player_cards) if player_cards else 0
    dealer_total = blackjack_hand_total(dealer_cards) if dealer_cards else 0
    if is_guest_mode:
        total_net = float(st.session_state.get("blackjack_guest_total_net", 0.0))
    else:
        blackjack_stats = get_account_stats(account, "blackjack") or {}
        total_net = float(blackjack_stats.get("total_game_net", 0.0))
    if round_state.get("status") == "player_turn":
        if len(dealer_cards) > 1:
            dealer_metric = f"{blackjack_hand_total(dealer_cards[1:])}+"
        else:
            dealer_metric = "?"
    else:
        dealer_metric = str(dealer_total)

    with st.sidebar:
        st.markdown("### Blackjack Stats")
        st.metric("Current bet", f"${format_money(round_state.get('bet', 0.0))}")
        st.metric("Player total", str(player_total))
        st.metric("Dealer showing", dealer_metric)
        st.metric("Total won/loss", f"${format_money(total_net)}")
        st.metric("Player cards", str(len(player_cards)))
        st.metric("Dealer cards", str(len(dealer_cards)))
        with st.expander("Round history"):
            history = round_state.get("history", [])
            if not history:
                st.write("No actions yet.")
            else:
                for entry in history:
                    st.write(entry)


def render_home_analytics_sidebar(account):
    with st.sidebar:
        st.markdown("### Account Analytics")
        selected_scope_label = st.selectbox(
            "View stats for",
            list(STAT_SCOPE_OPTIONS.keys()),
            key="home_stats_scope_filter",
        )
        selected_scope = STAT_SCOPE_OPTIONS[selected_scope_label]
        stats = get_account_stats(account, selected_scope)
        if stats is None:
            return

        balance = get_account_value(account)
        rounds_played = int(stats.get("rounds_played", 0))
        rounds_won = int(stats.get("rounds_won", 0))
        total_game_net = float(stats.get("total_game_net", 0.0))
        total_paid = float(stats.get("total_game_buy_in", 0.0))
        total_received = float(stats.get("total_game_payout", 0.0))
        win_percentage = float(stats.get("current_win_percentage", 0.0))

        st.metric("Signed in as", account)
        if balance is None:
            st.metric("Current balance", "N/A")
        else:
            st.metric("Current balance", f"${format_money(balance)}")
        st.caption(f"Showing: {selected_scope_label}")
        st.metric("Win rate", f"{win_percentage:.1f}%")
        st.metric("Game-only P/L", f"${format_money(total_game_net)}")
        st.metric("Rounds won", f"{rounds_won}/{rounds_played}")
        st.metric("Total paid to play", f"${format_money(total_paid)}")
        st.metric("Total won from games", f"${format_money(total_received)}")


def render_back_button():
    # Back button is hidden while a guessing round is actively running.
    if is_guessing_in_progress():
        return

    if not st.session_state.get("show_auth_flow") and st.session_state.get("active_action") == "Home":
        return

    if st.button("Back", key="global_back_home", use_container_width=False):
        account = st.session_state.get("current_account")
        if account:
            auto_remove_blackjack_lan_player(account)
        st.session_state["show_auth_flow"] = False
        st.session_state["auth_flow_mode"] = None
        st.session_state["pending_new_account"] = None
        st.session_state["active_action"] = "Home"
        end_guest_session(set_completion_message=True)
        _fast_rerun()


def auth_ui():
    if st.session_state.get("storage_unavailable", False):
        st.error("Sign-in and account creation are temporarily unavailable. Please use Guest mode.")
        return
    st.subheader("Sign In / Create Account")
    flow_mode = st.session_state.get("auth_flow_mode")

    if flow_mode is None:
        st.write("Do you already have an account?")
        yes_col, no_col = st.columns(2)
        if yes_col.button("Yes, sign in", key="auth_choose_sign_in", use_container_width=True):
            st.session_state["auth_flow_mode"] = "sign_in"
            _fast_rerun()
        if no_col.button("No, create account", key="auth_choose_create", use_container_width=True):
            st.session_state["auth_flow_mode"] = "create_account"
            _fast_rerun()
        return

    if flow_mode == "sign_in":
        with st.form("auth_sign_in_form"):
            account = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in")

        if submitted:
            account = account.strip()
            st.session_state["pending_force_sign_in_account"] = None
            if not account:
                st.error("Username is required.")
                return
            if not password:
                st.error("Password is required.")
                return
            if is_reserved_account_name(account):
                st.error("That account name is reserved.")
                return
            stored_password = get_account_password(account)
            if stored_password is None:
                st.error("No account found with that username. Choose account creation instead.")
                return
            if stored_password == "":
                if not set_account_password(account, password):
                    st.error("Failed to save password.")
                    return
                acquired, reason = acquire_account_session(account, _current_session_id())
                if not acquired:
                    if reason == "in_use":
                        st.error("That account is already signed in from another session.")
                        st.session_state["pending_force_sign_in_account"] = account
                        _fast_rerun()
                    else:
                        st.error("Failed to start your session. Please try again.")
                    return
                st.session_state["current_account"] = account
                st.session_state["settings_loaded_for_account"] = None
                st.session_state["redirect_to_home"] = True
                st.session_state["show_auth_flow"] = False
                st.session_state["auth_flow_mode"] = None
                st.success(f"Signed in as {account}.")
                _fast_rerun()
                return
            if password == stored_password:
                acquired, reason = acquire_account_session(account, _current_session_id())
                if not acquired:
                    if reason == "in_use":
                        st.error("That account is already signed in from another session.")
                        st.session_state["pending_force_sign_in_account"] = account
                        _fast_rerun()
                    else:
                        st.error("Failed to start your session. Please try again.")
                    return
                st.session_state["current_account"] = account
                st.session_state["settings_loaded_for_account"] = None
                st.session_state["redirect_to_home"] = True
                st.session_state["show_auth_flow"] = False
                st.session_state["auth_flow_mode"] = None
                st.success(f"Signed in as {account}.")
                _fast_rerun()
                return
            st.error("Incorrect password.")

        pending_force_account = st.session_state.get("pending_force_sign_in_account")
        if pending_force_account:
            st.warning(f"'{pending_force_account}' appears active elsewhere.")
            if st.button(
                "Force sign in and end other session",
                key="auth_force_sign_in",
                use_container_width=True,
            ):
                forced, reason = force_acquire_account_session(pending_force_account, _current_session_id())
                if not forced:
                    if reason == "account_not_found":
                        st.error("Account no longer exists.")
                    else:
                        st.error("Could not force sign in. Please try again.")
                    return
                st.session_state["current_account"] = pending_force_account
                st.session_state["settings_loaded_for_account"] = None
                st.session_state["redirect_to_home"] = True
                st.session_state["show_auth_flow"] = False
                st.session_state["auth_flow_mode"] = None
                st.session_state["pending_force_sign_in_account"] = None
                st.success(f"Signed in as {pending_force_account}.")
                _fast_rerun()
                return

    if flow_mode == "create_account":
        with st.form("auth_create_account_form"):
            account = st.text_input("Choose a username")
            password = st.text_input("Choose a password", type="password")
            confirm_password = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account")

        if submitted:
            account = account.strip()
            if not account:
                st.error("Username is required.")
                return
            if is_reserved_account_name(account):
                st.error("That account name is reserved.")
                return
            if not password:
                st.error("Password is required.")
                return
            if password != confirm_password:
                st.error("Password confirmation does not match.")
                return
            if get_account_value(account) is not None:
                st.error("An account with that username already exists.")
                return
            starting_balance = house_round_credit(0.0)
            if not create_account_record(account, starting_balance, password):
                st.error("Failed to create account.")
                return
            acquired, reason = acquire_account_session(account, _current_session_id())
            if not acquired:
                if reason == "in_use":
                    st.error("That account is already signed in from another session.")
                else:
                    st.error("Failed to start your session. Please try signing in again.")
                return
            st.session_state["current_account"] = account
            st.session_state["settings_loaded_for_account"] = None
            st.session_state["redirect_to_home"] = True
            st.session_state["show_auth_flow"] = False
            st.session_state["auth_flow_mode"] = None
            st.success(f"Account created and signed in as {account}.")
            _fast_rerun()
            return


def lookup_account_ui():
    st.subheader("Look Up Account")
    with st.form("lookup_form"):
        account = st.text_input("Account name")
        submitted = st.form_submit_button("Look up")
    if not submitted:
        return
    account = account.strip()
    accounts_snapshot = get_accounts_snapshot()
    account_entry = accounts_snapshot.get(account)
    if account_entry is None:
        st.error("Account not found.")
    else:
        value = float(account_entry.get("balance", 0.0))
        rankings = [(name, float(entry.get("balance", 0.0))) for name, entry in accounts_snapshot.items()]
        rankings.sort(key=lambda item: (-item[1], item[0].lower()))

        place = None
        previous_value = None
        previous_place = None
        for index, (name, stored_value) in enumerate(rankings):
            if previous_value is not None and stored_value == previous_value:
                current_place = previous_place
            else:
                current_place = index + 1
            if name == account:
                place = current_place
                break
            previous_value = stored_value
            previous_place = current_place

        if place is None:
            st.info(f"Balance: ${format_money(value)}")
            return
        st.info(f"Place: #{place} | Balance: ${format_money(value)}")


def add_withdraw_ui():
    st.subheader("Add / Withdraw")
    account = st.session_state["current_account"]
    if account is None:
        st.warning("Sign in first.")
        return

    with st.form("add_withdraw_form"):
        password = st.text_input("Re-enter password", type="password")
        amount = st.number_input("Amount (positive add, negative withdraw)", value=0.0, step=1.0, format="%.2f")
        submitted = st.form_submit_button("Apply change")

    if not submitted:
        return

    stored_password = get_account_password(account)
    if stored_password is None:
        st.error("Account not found.")
        return
    if password != stored_password:
        st.error("Authentication failed.")
        return
    balance = get_account_value(account)
    if balance is None:
        st.error("Account not found.")
        return
    # Manual withdrawals are always debt-safe, regardless of game debt settings.
    if amount < 0:
        if float(balance) < 0:
            st.error("You cannot withdraw while your balance is negative. Add funds first.")
            return
        if float(balance) + float(amount) < 0:
            st.error("Insufficient funds. You cannot withdraw more than your current balance.")
            return
    if not add_account_value(account, amount):
        st.error("Account not found.")
        return

    updated_balance = get_account_value(account)
    st.success(f"Updated balance: ${format_money(updated_balance)}")


def change_password_ui():
    st.subheader("Change Password")
    account = st.session_state["current_account"]
    if account is None:
        st.warning("Sign in first.")
        return

    with st.form("change_password_form"):
        current_password = st.text_input("Current password", type="password")
        new_password = st.text_input("New password", type="password")
        confirm_password = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password")

    if not submitted:
        return

    stored_password = get_account_password(account)
    if stored_password is None:
        st.error("Account not found.")
        return
    if current_password != stored_password:
        st.error("Current password is incorrect.")
        return
    if not new_password:
        st.error("New password is required.")
        return
    if new_password != confirm_password:
        st.error("New password confirmation does not match.")
        return
    if not set_account_password(account, new_password):
        st.error("Failed to update password.")
        return
    st.success("Password updated.")


def change_profile_picture_ui():
    st.subheader("Change Profile Picture")
    account = st.session_state["current_account"]
    if account is None:
        st.warning("Sign in first.")
        return

    current_avatar = _profile_avatar_display_text(account)
    st.caption(f"Current avatar: {current_avatar}")

    control_col, _spacer = st.columns([1.9, 4.1])
    with control_col:
        if st.button("Use initial letter", key="avatar_clear_to_initial", use_container_width=True):
            st.session_state["setting_profile_avatar"] = ""
            _persist_ui_settings_for_current_account()
            st.success("Profile picture cleared. Using your initial.")
            _fast_rerun()

    search_text = st.text_input(
        "Search avatars (name, tag, emoji)",
        key="avatar_search_query",
        placeholder="Try: fox, space, robot, food, sports...",
    )

    category_groups, total_count = _group_avatar_options(search_text)
    st.caption(f"{total_count} avatar options")
    if not category_groups:
        st.info("No avatars matched that search.")
        return

    _render_avatar_category_nav(category_groups)

    cols_per_row = 5
    for slug, label, options in category_groups:
        st.markdown(
            f'<div id="avatar-category-{slug}" style="scroll-margin-top: 5.5rem;"></div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"#### {label}")
        for row_start in range(0, len(options), cols_per_row):
            row = options[row_start : row_start + cols_per_row]
            columns = st.columns(cols_per_row)
            for index, (avatar_id, emoji, name) in enumerate(row):
                with columns[index]:
                    is_selected = st.session_state.get("setting_profile_avatar", "") == avatar_id
                    button_label = f"{emoji} {name}"
                    if is_selected:
                        button_label = f"Selected: {emoji} {name}"
                    if st.button(button_label, key=f"avatar_option_{avatar_id}", use_container_width=True):
                        st.session_state["setting_profile_avatar"] = avatar_id
                        _persist_ui_settings_for_current_account()
                        st.success(f"Updated profile picture to {emoji} {name}.")
                        _fast_rerun()
        st.markdown("---")


def odds_calculator_ui():
    st.subheader("Calculate Odds")
    col1, col2, col3 = st.columns(3)
    with col1:
        num_range = st.number_input("Range max", min_value=1, value=10, step=1)
    with col2:
        price_per_round = st.number_input("Price per round ($)", min_value=0.0, value=1.0, step=1.0, format="%.2f")
    with col3:
        guesses = st.number_input("Guesses", min_value=1, value=3, step=1)

    payout = calculate_payout(int(num_range), float(price_per_round), int(guesses))
    payout = house_round_credit(payout)
    st.info(f"Break-even payout: ${format_money(payout)}")
    st.caption("* These are break-even odds and may be adjusted to benefit the house.")


def leaderboards_ui():
    st.subheader("Leaderboards")
    selected_scope_label = st.selectbox(
        "Game scope",
        list(STAT_SCOPE_OPTIONS.keys()),
        key="leaderboard_game_scope_filter",
    )
    selected_scope = STAT_SCOPE_OPTIONS[selected_scope_label]
    accounts_snapshot = get_accounts_snapshot(selected_scope)
    if not accounts_snapshot:
        st.info("No accounts found.")
        return

    metric_options = {
        "Current amount": {
            "value_getter": lambda account_data: float(account_data.get("balance", 0.0)),
            "formatter": lambda value: f"${format_money(value)}",
            "you_ranked_label": "You are ranked",
        },
        "Win percentage": {
            "value_getter": lambda account_data: float(account_data.get("stats", {}).get("current_win_percentage", 0.0)),
            "formatter": lambda value: f"{value:.1f}%",
            "you_ranked_label": "You are ranked",
        },
        "Amount gained": {
            "value_getter": lambda account_data: float(account_data.get("stats", {}).get("total_game_net", 0.0)),
            "formatter": lambda value: f"${format_money(value)}",
            "you_ranked_label": "Your position",
        },
    }
    selected_metric = st.selectbox(
        "Rank by",
        list(metric_options.keys()),
        key="leaderboard_stat_filter",
    )
    selected_config = metric_options[selected_metric]

    rankings = []
    for name, account_data in accounts_snapshot.items():
        metric_value = selected_config["value_getter"](account_data)
        rankings.append((name, float(metric_value)))

    rankings.sort(key=lambda item: (-item[1], item[0].lower()))

    current_account = st.session_state.get("current_account")
    ranked_rows = []
    previous_value = None
    previous_place = None
    for index, (name, value) in enumerate(rankings):
        if previous_value is not None and value == previous_value:
            place = previous_place
        else:
            place = index + 1
        ranked_rows.append((place, name, value))
        previous_value = value
        previous_place = place

    rank_by_name = {name: place for place, name, _value in ranked_rows}
    index_by_name = {name: index for index, (_place, name, _value) in enumerate(ranked_rows)}
    display_value = selected_config["formatter"]

    st.markdown(f"#### Top 10 ({selected_metric} | {selected_scope_label})")
    top_ten = ranked_rows[:10]
    for place, name, value in top_ten:
        marker = " <- you" if current_account == name else ""
        st.write(f"{place}. {name} - {display_value(value)}{marker}")

    st.markdown("---")
    st.markdown("#### Around You")
    if current_account is None or current_account not in rank_by_name:
        st.info("Sign in to see players around your rank.")
        return

    current_place = rank_by_name[current_account]
    current_index = index_by_name[current_account]
    st.write(
        f"{selected_config['you_ranked_label']} #{current_place} by {selected_metric.lower()} "
        f"({selected_scope_label.lower()})."
    )

    above_entry = ranked_rows[current_index - 1] if current_index > 0 else None
    below_entry = ranked_rows[current_index + 1] if current_index + 1 < len(ranked_rows) else None

    if above_entry is not None:
        above_place, above_name, above_value = above_entry
        st.write(f"{above_place}. {above_name} - {display_value(above_value)}")
    else:
        st.write("No player above you.")

    current_value = ranked_rows[current_index][2]
    st.write(f"{current_place}. {current_account} - {display_value(current_value)} <- you")

    if below_entry is not None:
        below_place, below_name, below_value = below_entry
        st.write(f"{below_place}. {below_name} - {display_value(below_value)}")
    else:
        st.write("No player below you.")


def _check_game_limits(num_range, buy_in, guesses, limits=None):
    """
    Check if game parameters exceed configured limits.
    Returns (is_valid, error_messages) where is_valid is bool and error_messages is list of strings.
    """
    if limits is None:
        limits = load_game_limits()
    messages = []
    
    if limits["max_range"] is not None and num_range > limits["max_range"]:
        messages.append(f"Range is too high. Maximum allowed: {limits['max_range']}")
    
    if limits["max_buy_in"] is not None and buy_in > limits["max_buy_in"]:
        messages.append(f"Buy-in is too high. Maximum allowed: ${format_money(limits['max_buy_in'])}")
    
    if limits["max_guesses"] is not None and guesses > limits["max_guesses"]:
        messages.append(f"Number of guesses is too high. Maximum allowed: {limits['max_guesses']}")
    
    return len(messages) == 0, messages


def player_guesses_game_ui(account, is_guest_mode):
    st.markdown("#### You guess the number")
    round_state = st.session_state.get("player_guess_round")

    if not round_state:
        current_limits = load_game_limits()
        num_range = st.number_input("Range max", min_value=1, step=1, key="player_setup_num_range")
        buy_in = st.number_input(
            "Buy-in per round ($)",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="player_setup_buy_in",
        )
        guesses = st.number_input("Guesses per round", min_value=1, step=1, key="player_setup_guesses")
        
        # Check game limits
        is_valid, limit_errors = _check_game_limits(int(num_range), float(buy_in), int(guesses), limits=current_limits)
        if not is_valid:
            st.error("Game parameters exceed limits:")
            for error in limit_errors:
                st.error(f"• {error}")
            return

        setup_raw_payout = calculate_payout(int(num_range), float(buy_in), int(guesses)) / st.session_state["odds"]
        setup_payout = max(house_round_credit(setup_raw_payout), float(buy_in))
        st.info(f"Payout on win: ${format_money(setup_payout)}")
        setup_confirmed = True
        if is_bet_confirmation_enabled():
            st.caption(f"You are about to place a ${format_money(float(buy_in))} bet.")
            setup_confirmed = st.checkbox("I confirm this bet", key="player_setup_bet_confirm")

        def _start_player_round(start_range, start_buy_in, start_guesses):
            initial_probability = compute_win_probability(int(start_range), int(start_guesses))
            st.session_state["player_guess_round"] = {
                "num_range": int(start_range),
                "buy_in": float(start_buy_in),
                "guesses_left": int(start_guesses),
                "starting_guesses": int(start_guesses),
                "number": randint(1, int(start_range)),
                "payout": max(
                    house_round_credit(
                        calculate_payout(int(start_range), float(start_buy_in), int(start_guesses))
                        / st.session_state["odds"]
                    ),
                    float(start_buy_in),
                ),
                "low": 1,
                "high": int(start_range),
                "status": "active",
                "last_message": None,
                "history": [
                    {
                        "attempt": 0,
                        "guess": None,
                        "result": "start",
                        "win_probability": initial_probability,
                    }
                ],
            }
            st.session_state["player_guess_input_text"] = ""
            _fast_rerun()

        if st.button("Start round", key="player_setup_start_round", use_container_width=True):
            if is_bet_confirmation_enabled() and not setup_confirmed:
                st.warning("Confirm your bet before starting the round.")
                return
            if is_guest_mode:
                current_guest_balance = float(st.session_state.get("guest_balance", 0.0))
                if current_guest_balance < float(buy_in):
                    st.error("Not enough guest funds to cover this buy-in.")
                    return
                st.session_state["guest_balance"] = current_guest_balance - float(buy_in)
            else:
                if not can_afford_account_charge(account, buy_in):
                    st.warning("Insufficient funds. Negative balance is disabled in settings.")
                    if st.button("Enable negative balance and start round", key="player_enable_debt_start"):
                        st.session_state["setting_allow_negative_balance"] = True
                        _persist_ui_settings_for_current_account()
                        if not add_account_value(account, -buy_in):
                            st.error("Failed to charge buy-in. Account not found.")
                            return
                        _start_player_round(num_range, buy_in, guesses)
                    return
                if not add_account_value(account, -buy_in):
                    st.error("Failed to charge buy-in. Account not found.")
                    return
            _start_player_round(num_range, buy_in, guesses)
        return

    if round_state["status"] != "active":
        if round_state.get("last_message"):
            st.info(round_state["last_message"])
        replay_confirmed = True
        if is_bet_confirmation_enabled():
            st.caption(f"Replay buy-in: ${format_money(float(round_state['buy_in']))}")
            replay_confirmed = st.checkbox("I confirm this replay bet", key="player_replay_bet_confirm")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Play again (same settings)"):
                if is_bet_confirmation_enabled() and not replay_confirmed:
                    st.warning("Confirm your replay bet before starting another round.")
                    return
                can_start = True
                if is_guest_mode:
                    current_guest_balance = float(st.session_state.get("guest_balance", 0.0))
                    if current_guest_balance < float(round_state["buy_in"]):
                        can_start = False
                    else:
                        st.session_state["guest_balance"] = current_guest_balance - float(round_state["buy_in"])
                else:
                    if not can_afford_account_charge(account, round_state["buy_in"]):
                        can_start = False
                    elif not add_account_value(account, -round_state["buy_in"]):
                        can_start = False

                if can_start:
                    st.session_state["player_guess_round"] = {
                        "num_range": round_state["num_range"],
                        "buy_in": round_state["buy_in"],
                        "guesses_left": round_state["starting_guesses"],
                        "starting_guesses": round_state["starting_guesses"],
                        "number": randint(1, round_state["num_range"]),
                        "payout": round_state["payout"],
                        "low": 1,
                        "high": round_state["num_range"],
                        "status": "active",
                        "last_message": None,
                        "history": [
                            {
                                "attempt": 0,
                                "guess": None,
                                "result": "start",
                                "win_probability": compute_win_probability(
                                    round_state["num_range"], round_state["starting_guesses"]
                                ),
                            }
                        ],
                    }
                    st.session_state["player_guess_input_text"] = ""
                    _fast_rerun()
                else:
                    if is_guest_mode:
                        st.error("Not enough guest funds to play another round.")
                    else:
                        if is_debt_allowed():
                            st.error("Failed to start new round.")
                        else:
                            st.warning("Insufficient funds. Negative balance is disabled in settings.")
                            if st.button(
                                "Enable negative balance and play another round",
                                key="player_enable_debt_replay",
                            ):
                                st.session_state["setting_allow_negative_balance"] = True
                                _persist_ui_settings_for_current_account()
                                if not add_account_value(account, -round_state["buy_in"]):
                                    st.error("Failed to start new round.")
                                else:
                                    st.session_state["player_guess_round"] = {
                                        "num_range": round_state["num_range"],
                                        "buy_in": round_state["buy_in"],
                                        "guesses_left": round_state["starting_guesses"],
                                        "starting_guesses": round_state["starting_guesses"],
                                        "number": randint(1, round_state["num_range"]),
                                        "payout": round_state["payout"],
                                        "low": 1,
                                        "high": round_state["num_range"],
                                        "status": "active",
                                        "last_message": None,
                                        "history": [
                                            {
                                                "attempt": 0,
                                                "guess": None,
                                                "result": "start",
                                                "win_probability": compute_win_probability(
                                                    round_state["num_range"], round_state["starting_guesses"]
                                                ),
                                            }
                                        ],
                                    }
                                    st.session_state["player_guess_input_text"] = ""
                                    _fast_rerun()
        with col2:
            if st.button("End round"):
                st.session_state["player_guess_round"] = None
                _fast_rerun()
        return

    render_player_analytics_sidebar(round_state)
    st.write(f"Payout on win: ${format_money(round_state['payout'])}")
    st.write(f"Guesses left: {round_state['guesses_left']}")

    with st.form("player_guess_submit_form", clear_on_submit=True):
        guess_text = st.text_input(
            "Your guess",
            key="player_guess_input_text",
        )
        guess_submitted = st.form_submit_button("Submit guess")

    if guess_submitted:
        try:
            guess = int(guess_text.strip())
        except (TypeError, ValueError):
            round_state["last_message"] = "Please enter a whole number."
            guess = None
        if guess is None:
            pass
        elif guess < 1 or guess > round_state["num_range"]:
            round_state["last_message"] = f"Please guess from 1 to {round_state['num_range']}."
        elif guess == round_state["number"]:
            show_win_confetti()
            if is_guest_mode:
                st.session_state["guest_balance"] = float(st.session_state.get("guest_balance", 0.0)) + float(
                    round_state["payout"]
                )
            else:
                add_account_value(account, round_state["payout"])
                record_game_result(account, round_state["buy_in"], round_state["payout"], True, "player_guess")
            round_state["status"] = "finished"
            net = round_state["payout"] - round_state["buy_in"]
            net_word = "made" if net >= 0 else "lost"
            round_state["last_message"] = (
                f"You won \\${format_money(round_state['payout'])} in total, "
                f"you {net_word} \\${format_money(abs(net))}."
            )
            attempts_used = round_state["starting_guesses"] - round_state["guesses_left"] + 1
            round_state["history"].append(
                {
                    "attempt": attempts_used,
                    "guess": guess,
                    "result": "correct",
                    "win_probability": 1.0,
                }
            )
        else:
            round_state["guesses_left"] -= 1
            if guess > round_state["number"]:
                round_state["last_message"] = None
                round_state["high"] = min(round_state["high"], guess - 1)
                result_label = "too high"
            else:
                round_state["last_message"] = None
                round_state["low"] = max(round_state["low"], guess + 1)
                result_label = "too low"

            remaining_numbers = max(0, round_state["high"] - round_state["low"] + 1)
            new_probability = compute_win_probability(remaining_numbers, round_state["guesses_left"])
            attempts_used = round_state["starting_guesses"] - round_state["guesses_left"]
            round_state["history"].append(
                {
                    "attempt": attempts_used,
                    "guess": guess,
                    "result": result_label,
                    "win_probability": new_probability,
                }
            )
            if round_state["guesses_left"] <= 0:
                round_state["status"] = "finished"
                if not is_guest_mode:
                    record_game_result(account, round_state["buy_in"], 0.0, False, "player_guess")
                round_state["last_message"] = (
                    f"You lost ${format_money(round_state['buy_in'])}. "
                    f"The number was {round_state['number']}."
                )

    guess_entries = [
        point for point in round_state.get("history", []) if point.get("result") in {"too high", "too low", "correct"}
    ]
    if guess_entries:
        st.markdown("#### Guess history")
        for point in guess_entries:
            st.write(f"Guess #{point['attempt']}: {point['guess']} ({point['result']})")

    if round_state.get("last_message"):
        st.info(round_state["last_message"])


def _run_computer_guess_round(account, is_guest_mode, settings):
    num_range = int(settings["num_range"])
    secret_number = int(settings["secret_number"])
    guesses_allowed = int(settings["guesses"])
    price_per_round = float(settings["price_per_round"])
    payout = float(settings["payout"])

    st.session_state["computer_guess_in_progress"] = True
    if is_guest_mode:
        current_guest_balance = float(st.session_state.get("guest_balance", 0.0))
        if current_guest_balance + price_per_round - payout < 0:
            st.session_state["computer_guess_in_progress"] = False
            return {"error": "This setup could make your guest balance go negative. Lower payout risk or add more funds."}
        st.session_state["guest_balance"] = current_guest_balance + price_per_round
    else:
        current_balance_value = get_account_value(account)
        if current_balance_value is None:
            st.session_state["computer_guess_in_progress"] = False
            return {"error": "Failed to load account."}
        if (not is_debt_allowed()) and (float(current_balance_value) + price_per_round - payout < 0):
            st.session_state["computer_guess_in_progress"] = False
            return {"error": "This setup could make your balance go negative. Negative balance is disabled in settings."}
        if not add_account_value(account, price_per_round):
            st.session_state["computer_guess_in_progress"] = False
            return {"error": "Failed to credit round payment. Account not found."}

    low = 1
    high = num_range
    guessed = False
    guesses_log = []
    history = [
        {
            "attempt": 0,
            "guess": None,
            "result": "start",
            "win_probability": compute_win_probability(num_range, guesses_allowed),
        }
    ]
    attempts_used = 0

    for attempt in range(1, guesses_allowed + 1):
        attempts_used = attempt
        if guesses_allowed == 1:
            guess = randint(1, num_range)
        elif attempt == guesses_allowed:
            if low > high:
                break
            guess = randint(low, high)
        else:
            if low > high:
                break
            guess = (low + high) // 2

        if guess == secret_number:
            guesses_log.append(f"Guess #{attempt}: {guess} (correct)")
            if is_guest_mode:
                st.session_state["guest_balance"] = float(st.session_state.get("guest_balance", 0.0)) - payout
            else:
                add_account_value(account, -payout)
            guessed = True
            history.append(
                {
                    "attempt": attempt,
                    "guess": guess,
                    "result": "correct",
                    "win_probability": 1.0,
                }
            )
            break
        if guess < secret_number:
            guesses_log.append(f"Guess #{attempt}: {guess} (too low)")
            low = guess + 1
            result_label = "too low"
        else:
            guesses_log.append(f"Guess #{attempt}: {guess} (too high)")
            high = guess - 1
            result_label = "too high"

        guesses_left = max(0, guesses_allowed - attempt)
        remaining_numbers = max(0, high - low + 1)
        history.append(
            {
                "attempt": attempt,
                "guess": guess,
                "result": result_label,
                "win_probability": compute_win_probability(remaining_numbers, guesses_left),
            }
        )

    if not is_guest_mode:
        if guessed:
            record_game_result(account, payout, price_per_round, False, "computer_guess")
        else:
            record_game_result(account, 0.0, price_per_round, True, "computer_guess")

    st.session_state["computer_guess_in_progress"] = False
    return {
        "guessed": guessed,
        "guesses_log": guesses_log,
        "attempts_used": attempts_used,
        "low": low,
        "high": high,
        "history": history,
    }


def computer_guesses_game_ui(account, is_guest_mode):
    st.markdown("#### Computer guesses your number")
    round_state = st.session_state.get("computer_guess_round")

    if not round_state:
        current_limits = load_game_limits()
        num_range = st.number_input("Range max", min_value=1, step=1, key="computer_setup_num_range")
        secret_number = st.number_input(
            "Your secret number",
            min_value=1,
            max_value=int(num_range) if int(num_range) >= 1 else 1,
            step=1,
            key="computer_setup_secret_number",
        )
        guesses = st.number_input("Computer guesses allowed", min_value=1, step=1, key="computer_setup_guesses")
        price_per_round = st.number_input(
            "Computer pays you per round ($)",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="computer_setup_price",
        )

        # Check game limits
        is_valid, limit_errors = _check_game_limits(
            int(num_range),
            float(price_per_round),
            int(guesses),
            limits=current_limits,
        )
        if not is_valid:
            st.error("Game parameters exceed limits:")
            for error in limit_errors:
                st.error(f"• {error}")
            return

        raw_payout = calculate_payout(int(num_range), float(price_per_round), int(guesses)) * st.session_state["odds"]
        payout = max(house_round_charge(raw_payout), float(price_per_round))
        st.info(f"If the computer wins, you lose: ${format_money(payout)}")
        setup_confirmed = True
        if is_bet_confirmation_enabled():
            st.caption(f"Max loss this round: ${format_money(float(payout))}")
            setup_confirmed = st.checkbox("I confirm this bet", key="computer_setup_bet_confirm")

        if st.button("Confirm settings", key="computer_setup_confirm", use_container_width=True):
            if is_bet_confirmation_enabled() and not setup_confirmed:
                st.warning("Confirm your bet before starting the round.")
                return
            settings = {
                "num_range": int(num_range),
                "secret_number": int(secret_number),
                "guesses": int(guesses),
                "price_per_round": float(price_per_round),
                "payout": float(payout),
            }
            round_result = _run_computer_guess_round(account, is_guest_mode, settings)
            if "error" in round_result:
                st.warning(round_result["error"])
                if (
                    "go negative" in round_result["error"].lower()
                    and st.button("Enable negative balance and continue", key="computer_enable_debt_start")
                ):
                    st.session_state["setting_allow_negative_balance"] = True
                    _persist_ui_settings_for_current_account()
                    round_result = _run_computer_guess_round(account, is_guest_mode, settings)
                    if "error" in round_result:
                        st.error(round_result["error"])
                        return
                    st.session_state["computer_guess_round"] = {
                        **settings,
                        **round_result,
                    }
                    _fast_rerun()
                return
            st.session_state["computer_guess_round"] = {
                **settings,
                **round_result,
            }
            _fast_rerun()
        return

    render_computer_analytics_sidebar(round_state)
    st.write(f"If the computer wins, you lose: ${format_money(round_state['payout'])}")
    for line in round_state.get("guesses_log", []):
        st.text(line)
    if round_state.get("guessed"):
        st.error("The computer guessed your number.")
    else:
        st.success("The computer failed to guess your number.")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Play another round (same secret)", key="computer_play_same_secret"):
            st.session_state["computer_guess_round"] = None
            st.session_state["computer_setup_num_range"] = int(round_state["num_range"])
            st.session_state["computer_setup_guesses"] = int(round_state["guesses"])
            st.session_state["computer_setup_price"] = float(round_state["price_per_round"])
            st.session_state["computer_setup_secret_number"] = int(round_state["secret_number"])
            _fast_rerun()
    with col2:
        if st.button("Play another round (choose new secret)", key="computer_play_another_round"):
            st.session_state["computer_guess_round"] = None
            st.session_state["computer_setup_num_range"] = int(round_state["num_range"])
            st.session_state["computer_setup_guesses"] = int(round_state["guesses"])
            st.session_state["computer_setup_price"] = float(round_state["price_per_round"])
            st.session_state["computer_setup_secret_number"] = randint(1, int(round_state["num_range"]))
            _fast_rerun()
    with col3:
        if st.button("Quit", key="computer_quit_rounds"):
            st.session_state["computer_guess_round"] = None
            st.session_state["selected_game_mode"] = None
            _fast_rerun()


def play_game_ui():
    st.subheader("Play the Number Guessing Game")
    account = st.session_state["current_account"]
    guest_mode_active = st.session_state.get("guest_mode_active", False)
    if account is None and not guest_mode_active:
        if not st.session_state.get("guest_mode_setup", False):
            st.warning("You are not signed in. Do you want to play in guest mode?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Yes, play as guest", key="guest_mode_yes", use_container_width=True):
                    st.session_state["guest_mode_setup"] = True
                    _fast_rerun()
            
            return

        with st.form("guest_mode_setup_form"):
            guest_buy_in = st.number_input(
                "How much money do you want to play with?",
                min_value=0.0,
                step=1.0,
                format="%.2f",
            )
            guest_submitted = st.form_submit_button("Start guest mode")
        if not guest_submitted:
            return
        st.session_state["guest_balance"] = float(guest_buy_in)
        st.session_state["guest_mode_active"] = True
        st.session_state["guest_mode_setup"] = False
        st.session_state["selected_game_mode"] = None
        st.success(f"Guest mode started with ${format_money(guest_buy_in)}.")
        _fast_rerun()

    is_guest_mode = account is None and st.session_state.get("guest_mode_active", False)

    selected_mode = st.session_state.get("selected_game_mode")
    if selected_mode is None:
        st.markdown("#### Choose game mode")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("You guess the number", use_container_width=True):
                st.session_state["selected_game_mode"] = "You guess the number"
                _fast_rerun()
        with col2:
            if st.button("Computer guesses your number", use_container_width=True):
                st.session_state["selected_game_mode"] = "Computer guesses your number"
                _fast_rerun()
        return

    if selected_mode == "You guess the number":
        player_guesses_game_ui(account, is_guest_mode)
    else:
        computer_guesses_game_ui(account, is_guest_mode)

    if is_guest_mode:
        guest_balance = float(st.session_state.get("guest_balance", 0.0))
        st.info(f"Guest balance: ${format_money(guest_balance)}")
    else:
        balance = current_balance()
        if balance is not None:
            st.info(f"Current balance: ${format_money(balance)}")


def blackjack_best_dealer_stop_total():
    # In standard blackjack, standing on all 17+ is the strongest long-run dealer rule.
    return BLACKJACK_DEALER_STAND_TOTAL


def blackjack_new_deck():
    deck = [(rank, suit) for suit in BLACKJACK_SUITS for rank in BLACKJACK_RANKS]
    shuffle(deck)
    return deck


def blackjack_draw_card(round_state):
    if not round_state["deck"]:
        round_state["deck"] = blackjack_new_deck()
    return round_state["deck"].pop()


def blackjack_hand_total(cards):
    total = 0
    aces = 0
    for rank, _suit in cards:
        if rank == "A":
            total += 11
            aces += 1
        elif rank in {"J", "Q", "K"}:
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def blackjack_is_natural(cards):
    return len(cards) == 2 and blackjack_hand_total(cards) == 21


def blackjack_format_hand(cards):
    return ", ".join(f"{rank}{suit}" for rank, suit in cards)


def blackjack_card_label(card):
    rank, suit = card
    suit_symbols = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
    symbol = suit_symbols.get(suit, suit)
    color = "red" if suit in {"H", "D"} else "black"
    return str(rank), symbol, color


def blackjack_render_hand_html(cards, hidden_indexes, animate_indexes, target):
    if not cards:
        return "<div class='bj-empty-slot'>No cards</div>"

    rendered_cards = []
    for index, card in enumerate(cards):
        classes = ["bj-card"]
        hidden = index in hidden_indexes
        if hidden:
            classes.append("bj-card-back")
            card_html = "<span class='bj-back-pattern'></span>"
        else:
            rank, suit_symbol, color = blackjack_card_label(card)
            classes.append("bj-card-red" if color == "red" else "bj-card-black")
            card_html = (
                "<div class='bj-card-face'>"
                f"<span class='bj-card-corner bj-card-corner-tl'>{rank}<small>{suit_symbol}</small></span>"
                f"<span class='bj-card-center'>{suit_symbol}</span>"
                f"<span class='bj-card-corner bj-card-corner-br'>{rank}<small>{suit_symbol}</small></span>"
                "</div>"
            )

        if index in animate_indexes:
            if target == "dealer":
                classes.append("bj-card-deal-dealer")
            else:
                classes.append("bj-card-deal-player")

        rendered_cards.append(f"<div class=\"{' '.join(classes)}\">{card_html}</div>")

    return "".join(rendered_cards)


def _blackjack_style_signature():
    return (
        st.session_state.get("theme_bj_label_color", "#ecfff9"),
        st.session_state.get("theme_bj_deck_color", "#d9f6ef"),
        st.session_state.get("theme_bj_deck_count_color", "rgba(237, 252, 247, 0.92)"),
        st.session_state.get("theme_bj_empty_slot_color", "rgba(241, 255, 250, 0.74)"),
    )


def _ensure_blackjack_shared_styles():
    bj_label_color, bj_deck_color, bj_deck_count_color, bj_empty_slot_color = _blackjack_style_signature()
    st.markdown(
        f"""
        <style>
        .bj-table-wrap,
        .bj-lan-wrap {{
            margin: 0.2rem 0 0.5rem 0;
            border-radius: 14px;
            padding: 0.56rem 0.62rem 0.62rem 0.62rem;
            background: linear-gradient(160deg, rgba(12, 64, 54, 0.78), rgba(7, 39, 33, 0.84));
            border: 1px solid rgba(136, 216, 188, 0.34);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
            overflow: hidden;
        }}
        .bj-lan-player-block {{
            margin-top: 0.4rem;
            padding-top: 0.38rem;
            border-top: 1px solid rgba(188, 233, 220, 0.2);
        }}
        .bj-lan-ring {{
            position: relative;
            min-height: 470px;
            border-radius: 16px;
            overflow: hidden;
            background:
                radial-gradient(ellipse at center, rgba(26, 97, 79, 0.72) 0%, rgba(12, 53, 43, 0.84) 58%, rgba(8, 37, 31, 0.9) 100%);
            border: 1px solid rgba(168, 225, 207, 0.24);
        }}
        .bj-lan-felt-oval {{
            position: absolute;
            left: 50%;
            top: 55%;
            transform: translate(-50%, -50%);
            width: min(95%, 860px);
            height: min(74%, 340px);
            border-radius: 999px;
            border: 2px solid rgba(194, 235, 222, 0.26);
            box-shadow:
                inset 0 0 0 2px rgba(14, 52, 44, 0.38),
                inset 0 -18px 34px rgba(0, 0, 0, 0.24);
            pointer-events: none;
        }}
        .bj-lan-dealer-seat {{
            position: absolute;
            left: 50%;
            top: 12%;
            transform: translate(-50%, -50%);
            width: min(92%, 430px);
            text-align: center;
            z-index: 2;
        }}
        .bj-lan-dealer-seat .bj-hand {{
            justify-content: center;
        }}
        .bj-lan-seats {{
            position: absolute;
            inset: 0;
        }}
        .bj-lan-seat {{
            position: absolute;
            transform: translate(-50%, -50%);
            width: min(90vw, 280px);
            max-width: 280px;
            padding: 0.4rem 0.45rem 0.45rem 0.45rem;
            border-radius: 12px;
            background: rgba(6, 35, 29, 0.44);
            border: 1px solid rgba(184, 232, 216, 0.2);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
            text-align: center;
            z-index: 2;
        }}
        .bj-lan-seat .bj-hand {{
            justify-content: center;
        }}
        .bj-lan-seat-current {{
            border-color: rgba(255, 231, 145, 0.92);
            box-shadow:
                0 0 0 2px rgba(255, 225, 120, 0.32),
                0 0 16px rgba(255, 214, 79, 0.3),
                inset 0 0 0 1px rgba(255, 255, 255, 0.05);
        }}
        .bj-lan-seat-self {{
            border-color: rgba(172, 236, 255, 0.86);
            box-shadow:
                0 0 0 1px rgba(105, 205, 236, 0.42),
                inset 0 0 0 1px rgba(255, 255, 255, 0.05);
        }}
        .bj-lan-turn-badge {{
            display: inline-block;
            margin-left: 0.35rem;
            padding: 0.08rem 0.34rem;
            border-radius: 999px;
            font-size: 0.66rem;
            font-weight: 800;
            letter-spacing: 0.03em;
            color: #1f1800;
            background: linear-gradient(135deg, #ffe18a 0%, #f7c84a 100%);
            vertical-align: middle;
        }}
        .bj-row {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.4rem;
            margin: 0.12rem 0;
            text-align: center;
        }}
        .bj-label {{
            width: 100%;
            font-weight: 700;
            letter-spacing: 0.01em;
            margin-bottom: 0.08rem;
            font-size: 0.9rem;
            color: {bj_label_color};
            text-align: center;
        }}
        .bj-hand {{
            min-height: 74px;
            width: 100%;
            display: flex;
            flex-wrap: wrap;
            gap: 0.32rem;
            align-items: center;
            justify-content: center;
        }}
        .bj-center {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            margin: 0.14rem 0 0.2rem 0;
        }}
        .bj-deck {{
            position: relative;
            width: 46px;
            height: 66px;
            border-radius: 7px;
            border: 1px solid rgba(211, 239, 228, 0.42);
            background: linear-gradient(165deg, #164e56 0%, #0e3442 100%);
            box-shadow: 0 7px 12px rgba(0, 0, 0, 0.24), inset 0 0 0 1px rgba(255, 255, 255, 0.1);
            color: {bj_deck_color};
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.68rem;
            letter-spacing: 0.03em;
        }}
        .bj-deck::before,
        .bj-deck::after {{
            content: "";
            position: absolute;
            border-radius: 7px;
            border: 1px solid rgba(211, 239, 228, 0.24);
            background: linear-gradient(165deg, #143d44 0%, #0c2b37 100%);
            width: 46px;
            height: 66px;
            left: -3px;
            top: -3px;
            z-index: -1;
        }}
        .bj-deck::after {{
            left: -6px;
            top: -6px;
            opacity: 0.75;
        }}
        .bj-deck-count {{
            margin-top: 0.16rem;
            font-size: 0.72rem;
            color: {bj_deck_count_color};
        }}
        .bj-card {{
            width: 46px;
            height: 66px;
            border-radius: 7px;
            border: 1px solid rgba(191, 210, 205, 0.85);
            background: linear-gradient(178deg, #fff 0%, #f2f8f4 100%);
            box-shadow: 0 5px 10px rgba(0, 0, 0, 0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 0.86rem;
            letter-spacing: 0.01em;
        }}
        .bj-card-face {{
            width: 100%;
            height: 100%;
            position: relative;
            display: block;
        }}
        .bj-card-corner {{
            position: absolute;
            display: flex;
            flex-direction: column;
            line-height: 0.85;
            font-weight: 800;
            font-size: 0.65rem;
        }}
        .bj-card-corner small {{
            font-size: 0.56rem;
            font-weight: 700;
        }}
        .bj-card-corner-tl {{
            top: 3px;
            left: 4px;
            align-items: flex-start;
        }}
        .bj-card-corner-br {{
            right: 4px;
            bottom: 3px;
            transform: rotate(180deg);
            align-items: flex-start;
        }}
        .bj-card-center {{
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.08rem;
            opacity: 0.9;
        }}
        .bj-card-black {{
            color: #102b24;
        }}
        .bj-card-red {{
            color: #a11f33;
        }}
        .bj-card-back {{
            border-color: rgba(166, 222, 208, 0.56);
            background: repeating-linear-gradient(
                45deg,
                #0f3f50,
                #0f3f50 6px,
                #1d5f6d 6px,
                #1d5f6d 12px
            );
        }}
        .bj-back-pattern {{
            width: 84%;
            height: 84%;
            border-radius: 6px;
            border: 1px solid rgba(207, 241, 231, 0.62);
            background: rgba(255, 255, 255, 0.08);
        }}
        .bj-empty-slot {{
            min-height: 66px;
            padding: 0.35rem 0.52rem;
            border-radius: 10px;
            border: 1px dashed rgba(199, 241, 229, 0.38);
            color: {bj_empty_slot_color};
            font-size: 0.74rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .bj-card-deal-player {{
            animation: bjDealPlayer 460ms cubic-bezier(0.22, 0.9, 0.28, 1) both;
        }}
        .bj-card-deal-dealer {{
            animation: bjDealDealer 460ms cubic-bezier(0.22, 0.9, 0.28, 1) both;
        }}
        @keyframes bjDealPlayer {{
            from {{
                transform: translate(-260px, -20px) scale(0.45) rotate(-5deg);
                opacity: 0.12;
            }}
            to {{
                transform: translate(0, 0) scale(1) rotate(0deg);
                opacity: 1;
            }}
        }}
        @keyframes bjDealDealer {{
            from {{
                transform: translate(-260px, 22px) scale(0.45) rotate(5deg);
                opacity: 0.12;
            }}
            to {{
                transform: translate(0, 0) scale(1) rotate(0deg);
                opacity: 1;
            }}
        }}
        @media (max-width: 700px) {{
            .bj-table-wrap,
            .bj-lan-wrap {{
                padding: 0.5rem;
            }}
            .bj-lan-ring {{
                min-height: 520px;
            }}
            .bj-lan-seat {{
                width: min(88vw, 235px);
                max-width: 235px;
            }}
            .bj-lan-dealer-seat {{
                width: min(92vw, 300px);
            }}
            .bj-card,
            .bj-deck,
            .bj-deck::before,
            .bj-deck::after {{
                width: 42px;
                height: 60px;
            }}
            .bj-card {{
                font-size: 0.78rem;
            }}
            @keyframes bjDealPlayer {{
                from {{
                    transform: translate(-160px, -14px) scale(0.52) rotate(-5deg);
                    opacity: 0.15;
                }}
                to {{
                    transform: translate(0, 0) scale(1) rotate(0deg);
                    opacity: 1;
                }}
            }}
            @keyframes bjDealDealer {{
                from {{
                    transform: translate(-160px, 14px) scale(0.52) rotate(5deg);
                    opacity: 0.15;
                }}
                to {{
                    transform: translate(0, 0) scale(1) rotate(0deg);
                    opacity: 1;
                }}
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
def render_blackjack_table(round_state):
    _ensure_blackjack_shared_styles()
    dealer_cards = round_state.get("dealer_cards", [])
    player_cards = round_state.get("player_cards", [])
    reveal_dealer_hole = round_state.get("status") != "player_turn"
    hidden_indexes = {0} if dealer_cards and not reveal_dealer_hole else set()

    dealer_visible_total = "?"
    if reveal_dealer_hole:
        dealer_visible_total = str(blackjack_hand_total(dealer_cards))
    elif len(dealer_cards) > 1:
        dealer_visible_total = f"{blackjack_hand_total(dealer_cards[1:])}+"

    player_total = blackjack_hand_total(player_cards) if player_cards else 0
    dealer_cards_html = blackjack_render_hand_html(
        dealer_cards,
        hidden_indexes,
        round_state.get("animate_dealer_indexes", []),
        "dealer",
    )
    player_cards_html = blackjack_render_hand_html(
        player_cards,
        set(),
        round_state.get("animate_player_indexes", []),
        "player",
    )

    st.markdown(
        f"""
        <div class="bj-table-wrap">
            <div class="bj-row">
                <div class="bj-label">Dealer ({dealer_visible_total})</div>
            </div>
            <div class="bj-row">
                <div class="bj-hand">{dealer_cards_html}</div>
            </div>
            <div class="bj-center">
                <div class="bj-deck">DECK</div>
                <div class="bj-deck-count">{len(round_state.get("deck", []))} cards left</div>
            </div>
            <div class="bj-row">
                <div class="bj-label">Player ({player_total})</div>
            </div>
            <div class="bj-row">
                <div class="bj-hand">{player_cards_html}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def settle_blackjack_round(account, round_state, result, message, is_guest_mode):
    bet = float(round_state["bet"])
    if result == "blackjack":
        payout = house_round_credit(bet * 2.5)
        won = True
    elif result == "win":
        payout = house_round_credit(bet * 2.0)
        won = True
    elif result == "push":
        payout = house_round_credit(bet)
        won = False
    else:
        payout = 0.0
        won = False
    round_net = float(payout) - float(bet)

    if is_guest_mode:
        if payout > 0:
            st.session_state["guest_balance"] = float(st.session_state.get("guest_balance", 0.0)) + float(payout)
        st.session_state["blackjack_guest_total_net"] = float(
            st.session_state.get("blackjack_guest_total_net", 0.0)
        ) + round_net
    else:
        if payout > 0 and not add_account_value(account, payout):
            return "Failed to settle payout. Account not found."
        if not record_game_result(account, bet, payout, won, "blackjack"):
            return "Failed to record the blackjack result."

    if won:
        show_win_confetti()

    round_state["status"] = "finished"
    round_state["result"] = result
    round_state["payout"] = payout
    round_state["message"] = message
    round_state.setdefault("history", []).append(message)
    # Reset to a full freshly shuffled deck after every hand.
    round_state["deck"] = blackjack_new_deck()
    return None


def start_blackjack_round(account, bet, is_guest_mode):
    if is_guest_mode:
        guest_balance = float(st.session_state.get("guest_balance", 0.0))
        if guest_balance < float(bet):
            return None, "Not enough guest funds to place that bet."
        st.session_state["guest_balance"] = guest_balance - float(bet)
    else:
        if not add_account_value(account, -bet):
            return None, "Failed to place bet. Account not found."

    round_state = {
        "account": account,
        "guest_mode": bool(is_guest_mode),
        "bet": float(bet),
        "deck": blackjack_new_deck(),
        "player_cards": [],
        "dealer_cards": [],
        "status": "player_turn",
        "dealer_stop_total": blackjack_best_dealer_stop_total(),
        "message": "",
        "result": None,
        "payout": 0.0,
        "animate_player_indexes": [],
        "animate_dealer_indexes": [],
        "history": [],
    }

    round_state["player_cards"].append(blackjack_draw_card(round_state))
    round_state["dealer_cards"].append(blackjack_draw_card(round_state))
    round_state["player_cards"].append(blackjack_draw_card(round_state))
    round_state["dealer_cards"].append(blackjack_draw_card(round_state))
    round_state["animate_player_indexes"] = [0, 1]
    round_state["animate_dealer_indexes"] = [0, 1]
    round_state["history"].append(f"Round started. Bet: ${format_money(bet)}.")
    if len(round_state["dealer_cards"]) > 1:
        round_state["history"].append(
            f"Initial hands dealt. Dealer showing {blackjack_hand_total(round_state['dealer_cards'][1:])}+."
        )

    player_natural = blackjack_is_natural(round_state["player_cards"])
    dealer_natural = blackjack_is_natural(round_state["dealer_cards"])
    if player_natural and dealer_natural:
        error = settle_blackjack_round(
            account,
            round_state,
            "push",
            "Both you and the dealer have blackjack. Push.",
            is_guest_mode,
        )
        if error:
            return None, error
    elif player_natural:
        error = settle_blackjack_round(
            account,
            round_state,
            "blackjack",
            "Blackjack! You win 3:2.",
            is_guest_mode,
        )
        if error:
            return None, error
    elif dealer_natural:
        error = settle_blackjack_round(
            account,
            round_state,
            "loss",
            "Dealer blackjack. You lose this round.",
            is_guest_mode,
        )
        if error:
            return None, error

    return round_state, None


def run_blackjack_dealer_turn(account, round_state, is_guest_mode):
    drawn_indexes = []
    drawn_cards = []
    while blackjack_hand_total(round_state["dealer_cards"]) < int(round_state["dealer_stop_total"]):
        round_state["dealer_cards"].append(blackjack_draw_card(round_state))
        drawn_cards.append(round_state["dealer_cards"][-1])
        drawn_indexes.append(len(round_state["dealer_cards"]) - 1)
    round_state["animate_dealer_indexes"] = drawn_indexes
    round_state["animate_player_indexes"] = []
    if drawn_cards:
        labels = ", ".join(blackjack_format_hand([card]) for card in drawn_cards)
        round_state.setdefault("history", []).append(f"Dealer drew: {labels}.")

    player_total = blackjack_hand_total(round_state["player_cards"])
    dealer_total = blackjack_hand_total(round_state["dealer_cards"])

    if dealer_total > 21:
        return settle_blackjack_round(
            account,
            round_state,
            "win",
            f"Dealer busted with {dealer_total}. You win.",
            is_guest_mode,
        )
    if dealer_total < player_total:
        return settle_blackjack_round(
            account,
            round_state,
            "win",
            f"Your {player_total} beats dealer {dealer_total}. You win.",
            is_guest_mode,
        )
    if dealer_total > player_total:
        return settle_blackjack_round(
            account,
            round_state,
            "loss",
            f"Dealer {dealer_total} beats your {player_total}. You lose.",
            is_guest_mode,
        )
    return settle_blackjack_round(
        account,
        round_state,
        "push",
        f"Push at {player_total}. Your bet is returned.",
        is_guest_mode,
    )


def blackjack_lan_phase_label(phase):
    labels = {
        "waiting_for_players": "Waiting for players",
        "waiting_for_bets": "Waiting for bets",
        "player_turns": "Player turns",
        "finished": "Round finished",
    }
    return labels.get(str(phase), "Unknown")


def blackjack_lan_current_turn_player(table):
    turn_order = table.get("turn_order", [])
    turn_index = int(table.get("turn_index", 0))
    if not isinstance(turn_order, list) or turn_index < 0 or turn_index >= len(turn_order):
        return None
    current_turn = turn_order[turn_index]
    if not isinstance(current_turn, str):
        return None
    return current_turn


def blackjack_lan_seconds_remaining(table, settings):
    if table.get("phase") != "player_turns" or not bool(table.get("in_progress")):
        return None
    timeout_setting = table.get("turn_timeout_seconds", settings.get("turn_timeout_seconds", 30))
    if timeout_setting is None:
        return None
    try:
        timeout_seconds = int(timeout_setting)
    except (TypeError, ValueError):
        timeout_seconds = 30
    timeout_seconds = max(5, timeout_seconds)
    try:
        started_epoch = float(table.get("turn_started_epoch", 0.0) or 0.0)
    except (TypeError, ValueError):
        started_epoch = 0.0
    if started_epoch <= 0:
        return timeout_seconds
    elapsed = time.time() - started_epoch
    remaining = int(timeout_seconds - elapsed)
    return max(0, remaining)


def blackjack_lan_ready_counts(table):
    players = list(table.get("players", []))
    ready = 0
    player_states = table.get("player_states", {})
    for player_name in players:
        state = player_states.get(player_name, {})
        if bool(state.get("ready", False)):
            ready += 1
    return ready, len(players)


def render_blackjack_lan_hands(table, viewer_player=None):
    _ensure_blackjack_shared_styles()
    dealer_cards = table.get("dealer_cards", [])
    reveal_dealer = table.get("phase") != "player_turns"
    dealer_hidden_indexes = set() if reveal_dealer else ({0} if dealer_cards else set())
    if reveal_dealer:
        dealer_total_text = str(blackjack_hand_total(dealer_cards)) if dealer_cards else "0"
    elif len(dealer_cards) > 1:
        dealer_total_text = f"{blackjack_hand_total(dealer_cards[1:])}+"
    else:
        dealer_total_text = "?"
    dealer_cards_html = blackjack_render_hand_html(dealer_cards, dealer_hidden_indexes, [], "dealer")

    current_turn_player = blackjack_lan_current_turn_player(table)
    players = list(table.get("players", []))
    viewer_in_players = isinstance(viewer_player, str) and viewer_player in players

    ordered_players = []
    if viewer_in_players:
        ordered_players.append(viewer_player)
        ordered_players.extend([name for name in players if name != viewer_player])
    else:
        ordered_players = players

    seat_positions = {}
    if viewer_in_players:
        seat_positions[viewer_player] = (50.0, 88.0)
        other_players = [name for name in ordered_players if name != viewer_player]
        other_count = len(other_players)
        if other_count == 1:
            seat_positions[other_players[0]] = (50.0, 24.0)
        elif other_count > 1:
            for index, player_name in enumerate(other_players):
                spread_progress = index / (other_count - 1)
                angle_deg = 210.0 + (120.0 * spread_progress)
                radians = math.radians(angle_deg)
                x = 50.0 + (41.0 * math.cos(radians))
                y = 56.0 + (31.0 * math.sin(radians))
                seat_positions[player_name] = (x, y)
    else:
        player_count = len(ordered_players)
        if player_count == 1:
            seat_positions[ordered_players[0]] = (50.0, 82.0)
        elif player_count > 1:
            for index, player_name in enumerate(ordered_players):
                spread_progress = index / (player_count - 1)
                angle_deg = 205.0 + (130.0 * spread_progress)
                radians = math.radians(angle_deg)
                x = 50.0 + (42.0 * math.cos(radians))
                y = 56.0 + (31.0 * math.sin(radians))
                seat_positions[player_name] = (x, y)

    player_blocks = []
    for player_name in ordered_players:
        player_state = table.get("player_states", {}).get(player_name, {})
        cards = player_state.get("cards", [])
        cards_html = blackjack_render_hand_html(cards, set(), [], "player")
        total = blackjack_hand_total(cards) if cards else 0
        status = str(player_state.get("status", "waiting")).replace("_", " ").title()
        bet = float(player_state.get("bet", 0.0))
        payout = float(player_state.get("payout", 0.0))
        result = player_state.get("result")
        turn_badge = (
            '<span class="bj-lan-turn-badge">TURN</span>'
            if player_name == current_turn_player
            else ""
        )
        you_label = " (You)" if viewer_in_players and player_name == viewer_player else ""
        result_text = f" | Result: {str(result).title()} | Payout: ${format_money(payout)}" if result else ""
        label = (
            f"{player_name}{you_label} {turn_badge} ({total})"
            f" | Bet: ${format_money(bet)} | Status: {status}{result_text}"
        )
        seat_x, seat_y = seat_positions.get(player_name, (50.0, 56.0))
        seat_classes = ["bj-lan-seat"]
        if player_name == current_turn_player:
            seat_classes.append("bj-lan-seat-current")
        if viewer_in_players and player_name == viewer_player:
            seat_classes.append("bj-lan-seat-self")
        player_blocks.append(
            (
                f'<div class="{" ".join(seat_classes)}" style="left:{seat_x:.2f}%; top:{seat_y:.2f}%;">'
                f'<div class="bj-row"><div class="bj-label">{label}</div></div>'
                f'<div class="bj-row"><div class="bj-hand">{cards_html}</div></div>'
                "</div>"
            )
        )
    players_html = "".join(player_blocks) if player_blocks else (
        "<div class='bj-lan-seat' style='left:50%; top:64%;'><div class='bj-empty-slot'>No players at this table.</div></div>"
    )

    st.markdown(
        f"""
        <div class="bj-lan-wrap bj-lan-ring">
            <div class="bj-lan-felt-oval"></div>
            <div class="bj-lan-dealer-seat">
                <div class="bj-row"><div class="bj-label">Dealer ({dealer_total_text})</div></div>
                <div class="bj-row"><div class="bj-hand">{dealer_cards_html}</div></div>
            </div>
            <div class="bj-center" style="position:absolute; left:50%; top:52%; transform:translate(-50%, -50%); z-index:1;">
                <div class="bj-deck">DECK</div>
                <div class="bj-deck-count">{len(table.get("deck", []))} cards left</div>
            </div>
            <div class="bj-lan-seats">{players_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def blackjack_ui():

    st.subheader("Blackjack")
    account = st.session_state.get("current_account")
    if account is not None and st.session_state.get("blackjack_multiplayer_guest_account"):
        _clear_blackjack_multiplayer_guest_account(delete_record=True)
    guest_mode_active = st.session_state.get("guest_mode_active", False)

    mode = st.session_state.get("blackjack_mode_select", "Single Player")
    if mode == "Remote Multiplayer (LAN)":
        mode = "Multiplayer"
        st.session_state["blackjack_mode_select"] = mode
    guest_multiplayer_account = st.session_state.get("blackjack_multiplayer_guest_account")
    if mode != "Multiplayer" and guest_multiplayer_account:
        _clear_blackjack_multiplayer_guest_account(delete_record=True)
        guest_multiplayer_account = None
    joined_lan_table = None
    multiplayer_player = account or guest_multiplayer_account
    if mode == "Multiplayer" and multiplayer_player is not None:
        joined_lan_table = find_blackjack_lan_table_for_player(multiplayer_player)
    is_lan_table_locked = joined_lan_table is not None
    in_progress_round = st.session_state.get("blackjack_round")
    is_blackjack_round_active = (
        mode == "Single Player"
        and isinstance(in_progress_round, dict)
        and in_progress_round.get("status") == "player_turn"
    )

    # --- Blackjack Mode Selection ---
    if is_blackjack_round_active:
        st.markdown("**Mode selection is locked while this round is in progress.**")
    elif is_lan_table_locked:
        st.markdown("**Mode selection is locked while you are seated at a multiplayer table. Leave table to switch modes.**")
    else:
        st.markdown("**Choose a mode:**")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Single Player", key="mode_single_player", use_container_width=True):
                st.session_state["blackjack_mode_select"] = "Single Player"
                _fast_rerun()
        with col2:
            if st.button("Hotseat Multiplayer", key="mode_hotseat", use_container_width=True):
                st.session_state["blackjack_mode_select"] = "Hotseat Multiplayer"
                _fast_rerun()
        with col3:
            if st.button("Multiplayer", key="mode_remote", use_container_width=True):
                st.session_state["blackjack_mode_select"] = "Multiplayer"
                _fast_rerun()
    mode = st.session_state.get("blackjack_mode_select", "Single Player")
    st.markdown(f"<div style='margin-top: 0.5rem; font-weight: bold; color: var(--text-color);'>Current mode: <span style='color: var(--primary-color);'>{mode}</span></div>", unsafe_allow_html=True)

    if mode == "Single Player":
        if account is None and not guest_mode_active:
            if not st.session_state.get("blackjack_guest_mode_setup", False):
                st.warning("You are not signed in. Do you want to play blackjack in guest mode?")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Yes, play as guest", key="blackjack_guest_mode_yes", use_container_width=True):
                        st.session_state["blackjack_guest_mode_setup"] = True
                        _fast_rerun()
                return

            with st.form("blackjack_guest_mode_setup_form"):
                guest_buy_in = st.number_input(
                    "How much money do you want to play with?",
                    min_value=0.0,
                    value=20.0,
                    step=1.0,
                    format="%.2f",
                    key="blackjack_guest_mode_starting_balance",
                )
                guest_submitted = st.form_submit_button("Start guest mode")
            if not guest_submitted:
                return
            st.session_state["guest_balance"] = float(guest_buy_in)
            st.session_state["guest_mode_active"] = True
            st.session_state["blackjack_guest_mode_setup"] = False
            st.session_state["blackjack_guest_total_net"] = 0.0
            st.success(f"Guest mode started with ${format_money(guest_buy_in)}.")
            _fast_rerun()

        is_guest_mode = account is None and st.session_state.get("guest_mode_active", False)
        if account is not None:
            st.session_state["blackjack_guest_mode_setup"] = False

        round_state = st.session_state.get("blackjack_round")
        if round_state:
            if bool(round_state.get("guest_mode", False)) != bool(is_guest_mode):
                st.session_state["blackjack_round"] = None
                round_state = None
            elif (not is_guest_mode) and round_state.get("account") != account:
                st.session_state["blackjack_round"] = None
                round_state = None

        if is_guest_mode:
            balance = float(st.session_state.get("guest_balance", 0.0))
        else:
            balance = get_account_value(account)
            if balance is None:
                st.error("Account not found.")
                return

        if is_guest_mode:
            st.info(f"Guest balance: ${format_money(balance)}")
        else:
            st.info(f"Current balance: ${format_money(balance)}")
    elif mode == "Hotseat Multiplayer":
        if account is None:
            st.warning("You must be signed in to use hotseat multiplayer.")
            return
        st.info("Hotseat multiplayer mode coming soon!")
        return

    elif mode == "Multiplayer":
        st.markdown("### Multiplayer Tables")
        if multiplayer_player is None:
            if not st.session_state.get("blackjack_multiplayer_guest_setup", False):
                st.warning("You are not signed in. Start a guest multiplayer session to join tables.")
                if st.button("Start as guest", key="blackjack_multiplayer_guest_start", use_container_width=True):
                    st.session_state["blackjack_multiplayer_guest_setup"] = True
                    _fast_rerun()
                return

            with st.form("blackjack_multiplayer_guest_setup_form"):
                guest_buy_in = st.number_input(
                    "Guest multiplayer starting balance ($)",
                    min_value=0.0,
                    value=20.0,
                    step=1.0,
                    format="%.2f",
                    key="blackjack_multiplayer_guest_starting_balance",
                )
                guest_submitted = st.form_submit_button("Start guest multiplayer")
            if not guest_submitted:
                return
            guest_alias = f"guest_multiplayer_{uuid.uuid4().hex[:10]}"
            try:
                created = create_account_record(guest_alias, house_round_credit(float(guest_buy_in)), "")
            except Exception:
                st.error("Guest multiplayer is unavailable right now. Please try again later.")
                return
            if not created:
                st.error("Could not start guest multiplayer session. Please try again.")
                return
            try:
                acquired, reason = acquire_account_session(guest_alias, _current_session_id())
            except Exception:
                delete_account(guest_alias)
                st.error("Guest multiplayer is unavailable right now. Please try again later.")
                return
            if not acquired:
                delete_account(guest_alias)
                if reason == "in_use":
                    st.error("Guest session alias collision. Please try again.")
                else:
                    st.error("Could not start guest multiplayer session.")
                return
            st.session_state["blackjack_multiplayer_guest_account"] = guest_alias
            st.session_state["blackjack_multiplayer_guest_setup"] = False
            st.success(f"Guest multiplayer started with ${format_money(guest_buy_in)}.")
            _fast_rerun()

        account = multiplayer_player
        if st.session_state.get("blackjack_multiplayer_guest_account") == account:
            acquired, reason = acquire_account_session(account, _current_session_id())
            if not acquired:
                _clear_blackjack_multiplayer_guest_account(delete_record=True)
                if reason == "in_use":
                    st.error("Your guest multiplayer session is already active elsewhere. Start a new guest session.")
                else:
                    st.error("Your guest multiplayer session expired. Start a new guest session.")
                return

        lan_settings = get_blackjack_lan_settings()
        tables = get_blackjack_lan_tables()
        joined_table = joined_lan_table
        spectate_table = None
        spectate_table_id = st.session_state.get("blackjack_lan_spectate_table_id")
        spectate_password = str(st.session_state.get("blackjack_lan_spectate_password", ""))
        global_spectators_enabled = bool(lan_settings.get("allow_spectators_by_default", True))

        if joined_table is not None:
            st.session_state["blackjack_lan_spectate_table_id"] = None
            st.session_state["blackjack_lan_spectate_password"] = ""
        elif spectate_table_id is not None:
            for table in tables:
                if int(table.get("id", -1)) == int(spectate_table_id):
                    spectate_table = table
                    break
            if spectate_table is None:
                st.session_state["blackjack_lan_spectate_table_id"] = None
                st.session_state["blackjack_lan_spectate_password"] = ""
            else:
                allowed, message = can_spectate_blackjack_lan_table(int(spectate_table_id), spectate_password)
                if not allowed:
                    st.warning(message)
                    st.session_state["blackjack_lan_spectate_table_id"] = None
                    st.session_state["blackjack_lan_spectate_password"] = ""
                    spectate_table = None

        if joined_table is None and spectate_table is None:
            refresh_col, _spacer, create_col = st.columns([1.4, 3.4, 1.8])
            with refresh_col:
                if st.button("Refresh tables", key="blackjack_lan_refresh_tables", use_container_width=True):
                    _fast_rerun()
            with create_col:
                with st.expander("Create table", expanded=False):
                    create_table_name = st.text_input(
                        "Table name",
                        max_chars=60,
                        placeholder="Enter a table name",
                        key="blackjack_lan_create_table_name",
                    )
                    create_max_players = st.number_input(
                        "Max players",
                        min_value=1,
                        max_value=8,
                        value=int(lan_settings.get("default_max_players", 5)),
                        step=1,
                        key="blackjack_lan_create_max_players",
                    )
                    create_min_bet = st.number_input(
                        "Minimum bet ($)",
                        min_value=0.01,
                        step=0.01,
                        value=float(lan_settings.get("default_min_bet", 0.01)),
                        format="%.2f",
                        key="blackjack_lan_create_min_bet",
                    )
                    create_has_max_bet = st.checkbox(
                        "Set a maximum bet",
                        value=lan_settings.get("default_max_bet") is not None,
                        key="blackjack_lan_create_has_max_bet",
                    )
                    if create_has_max_bet:
                        default_max_bet = lan_settings.get("default_max_bet")
                        if default_max_bet is None:
                            default_max_bet = max(float(create_min_bet), 10.0)
                        create_max_bet = st.number_input(
                            "Maximum bet ($)",
                            min_value=float(create_min_bet),
                            step=0.01,
                            value=float(default_max_bet),
                            format="%.2f",
                            key="blackjack_lan_create_max_bet",
                        )
                    else:
                        create_max_bet = None
                    create_allow_spectators = st.checkbox(
                        "Allow spectators",
                        value=True,
                        key="blackjack_lan_create_allow_spectators",
                    )
                    create_no_timer = st.checkbox(
                        "No turn time requirement",
                        value=False,
                        key="blackjack_lan_create_no_timer",
                    )
                    if not create_no_timer:
                        create_turn_timeout = st.number_input(
                            "Turn timer (seconds)",
                            min_value=5,
                            max_value=300,
                            value=int(lan_settings.get("turn_timeout_seconds", 30)),
                            step=1,
                            key="blackjack_lan_create_turn_timeout",
                        )
                    else:
                        create_turn_timeout = None
                    create_timeout_penalty = st.number_input(
                        "Timeout penalty (% of player bet)",
                        min_value=0.0,
                        max_value=100.0,
                        value=float(lan_settings.get("timeout_penalty_percent", 25.0)),
                        step=1.0,
                        format="%.1f",
                        key="blackjack_lan_create_timeout_penalty",
                        disabled=create_no_timer,
                    )
                    create_spectator_password_required = st.checkbox(
                        "Spectators must enter table password",
                        value=False,
                        key="blackjack_lan_create_spectator_password_required",
                    )
                    create_private = st.checkbox(
                        "Private table (password protected)",
                        value=False,
                        key="blackjack_lan_create_private",
                    )
                    if create_private or create_spectator_password_required:
                        create_password = st.text_input(
                            "Table password",
                            type="password",
                            key="blackjack_lan_create_password",
                        )
                    else:
                        create_password = ""
                    if st.button("Create table", key="blackjack_lan_create_submit", use_container_width=True):
                        ok, message = create_blackjack_lan_table(
                            max_players=int(create_max_players),
                            min_bet=house_round_charge(float(create_min_bet)),
                            max_bet=house_round_charge(float(create_max_bet)) if create_max_bet is not None else None,
                            allow_spectators=create_allow_spectators,
                            spectators_require_password=create_spectator_password_required,
                            is_private=create_private,
                            password=create_password,
                            table_name=create_table_name,
                            turn_timeout_seconds=int(create_turn_timeout) if create_turn_timeout is not None else None,
                            timeout_penalty_percent=float(create_timeout_penalty),
                            disable_turn_timeout=bool(create_no_timer),
                        )
                        if ok:
                            st.success(message)
                        else:
                            st.error(message)
                        _fast_rerun()
            table_search = st.text_input(
                "Search table names",
                key="blackjack_lan_table_search",
                placeholder="Type a table name",
            ).strip().lower()
            st.caption("Join a table to play multiplayer with other users on this app URL.")
            visible_tables = []
            for table in tables:
                table_id = int(table["id"])
                table_name = str(table.get("name", f"Table {table_id}")).strip() or f"Table {table_id}"
                if table_search and table_search not in table_name.lower():
                    continue
                visible_tables.append(table)
            if not visible_tables:
                st.info("No tables match your search.")
            for table in visible_tables:
                table_id = int(table["id"])
                table_name = str(table.get("name", f"Table {table_id}")).strip() or f"Table {table_id}"
                players = table.get("players", [])
                pending_players = table.get("pending_players", [])
                max_players = int(table.get("max_players", 5))
                phase_label = blackjack_lan_phase_label(table.get("phase"))
                min_bet = float(table.get("min_bet", 0.01))
                max_bet = table.get("max_bet")
                table_turn_timeout = table.get("turn_timeout_seconds", lan_settings.get("turn_timeout_seconds", 30))
                table_timeout_penalty = float(
                    table.get("timeout_penalty_percent", lan_settings.get("timeout_penalty_percent", 25.0))
                )
                can_spectate_table = global_spectators_enabled and bool(table.get("allow_spectators", True))
                is_private = bool(table.get("is_private", False))
                spectators_require_password = bool(table.get("spectators_require_password", False))
                st.write(
                    f"{table_name} (ID {table_id}) | {len(players)}/{max_players} players | {phase_label}"
                )
                if max_bet is None:
                    st.caption(f"Bet limits: min ${format_money(min_bet)} | max none")
                else:
                    st.caption(f"Bet limits: min ${format_money(min_bet)} | max ${format_money(float(max_bet))}")
                if table_turn_timeout is None:
                    st.caption("Turn timer: none")
                else:
                    st.caption(
                        f"Turn timer: {int(table_turn_timeout)}s | Timeout penalty: {table_timeout_penalty:.1f}%"
                    )
                if players:
                    st.caption("Players: " + ", ".join(players))
                else:
                    st.caption("No players yet.")
                if pending_players:
                    st.caption("Queued for next hand: " + ", ".join(pending_players))
                if is_private:
                    st.caption("Private table (password required).")
                elif spectators_require_password:
                    st.caption("Spectators require table password.")

                table_password = ""
                if is_private or spectators_require_password:
                    table_password = st.text_input(
                        f"Password for {table_name}",
                        type="password",
                        key=f"blackjack_lan_table_password_{table_id}",
                    )

                is_full = len(players) + len(pending_players) >= max_players
                if is_admin_user():
                    join_col, spectate_col, admin_delete_col = st.columns(3)
                else:
                    join_col, spectate_col = st.columns(2)
                    admin_delete_col = None
                with join_col:
                    if st.button(
                        f"Join {table_name}",
                        key=f"blackjack_lan_join_table_{table_id}",
                        use_container_width=True,
                        disabled=is_full,
                    ):
                        joined, message = join_blackjack_lan_table(table_id, account, table_password)
                        if joined:
                            st.session_state["blackjack_lan_spectate_table_id"] = None
                            st.session_state["blackjack_lan_spectate_password"] = ""
                            st.success(message)
                        else:
                            st.error(message)
                        _fast_rerun()
                with spectate_col:
                    if st.button(
                        f"Spectate {table_name}",
                        key=f"blackjack_lan_spectate_table_{table_id}",
                        use_container_width=True,
                        disabled=(not can_spectate_table),
                    ):
                        allowed, message = can_spectate_blackjack_lan_table(table_id, table_password)
                        if allowed:
                            st.session_state["blackjack_lan_spectate_table_id"] = table_id
                            st.session_state["blackjack_lan_spectate_password"] = table_password
                            st.success("Now spectating this table.")
                        else:
                            st.error(message)
                        _fast_rerun()
                if admin_delete_col is not None:
                    with admin_delete_col:
                        if st.button(
                            "Delete table",
                            key=f"blackjack_lan_delete_table_lobby_{table_id}",
                            use_container_width=True,
                        ):
                            deleted, message = delete_blackjack_lan_table(table_id)
                            if deleted:
                                st.success(message)
                            else:
                                st.error(message)
                            _fast_rerun()
                st.markdown("---")
            return

        table_to_view = joined_table if joined_table is not None else spectate_table
        if table_to_view is None:
            st.warning("Unable to load table.")
            return
        table_id = int(table_to_view["id"])
        is_spectator_view = joined_table is None
        membership = str(joined_table.get("membership", "seated")) if joined_table is not None else "spectator"

        if is_spectator_view:
            st.info(f"Spectating Table {table_id}")
            if st.button("Stop spectating", key=f"blackjack_lan_stop_spectating_{table_id}", use_container_width=True):
                st.session_state["blackjack_lan_spectate_table_id"] = None
                st.session_state["blackjack_lan_spectate_password"] = ""
                _fast_rerun()
        else:
            if membership == "pending":
                st.success(f"You are queued for Table {table_id}.")
            else:
                st.success(f"You are seated at Table {table_id}.")

            if st.button("Leave table", key=f"blackjack_lan_leave_{table_id}", use_container_width=True):
                left, message = leave_blackjack_lan_table(table_id, account)
                if left:
                    st.success(message)
                else:
                    st.error(message)
                if st.session_state.get("blackjack_multiplayer_guest_account") == account:
                    _clear_blackjack_multiplayer_guest_account(delete_record=True)
                _fast_rerun()

        players = table_to_view.get("players", [])
        pending_players = table_to_view.get("pending_players", [])
        current_turn_player = blackjack_lan_current_turn_player(table_to_view)
        current_balance = get_account_value(account)
        seconds_left = blackjack_lan_seconds_remaining(table_to_view, lan_settings)
        table_turn_timeout = table_to_view.get("turn_timeout_seconds", lan_settings.get("turn_timeout_seconds", 30))
        timer_text = f"{seconds_left}s" if seconds_left is not None else ("No timer" if table_turn_timeout is None else "-")
        st.caption(
            f"Round {int(table_to_view.get('round', 0))} | "
            f"{blackjack_lan_phase_label(table_to_view.get('phase'))} | "
            f"Turn: {current_turn_player or '-'} ({timer_text}) | "
            f"Balance: ${format_money(current_balance) if current_balance is not None else 'N/A'}"
        )
        penalty_percent = float(
            table_to_view.get("timeout_penalty_percent", lan_settings.get("timeout_penalty_percent", 25.0))
        )
        timeout_caption = (
            "No timer"
            if table_turn_timeout is None
            else f"{int(table_turn_timeout)}s timer"
        )
        st.caption(
            "Players: "
            + (", ".join(players) if players else "No players")
            + (f" | Queue: {', '.join(pending_players)}" if pending_players else "")
            + f" | {timeout_caption}"
            + (f" | Timeout penalty: {penalty_percent:.1f}% + ejection" if table_turn_timeout is not None else "")
        )
        if membership == "pending":
            st.info("A hand is currently in progress. You will join automatically on the next hand.")

        player_state = table_to_view.get("player_states", {}).get(account, {})
        current_bet = float(player_state.get("bet", 0.0))
        if (not is_spectator_view) and membership == "seated" and (not bool(table_to_view.get("in_progress"))):
            with st.form(f"blackjack_lan_bet_form_{table_id}"):
                table_min_bet = float(table_to_view.get("min_bet", 0.01))
                table_max_bet = table_to_view.get("max_bet")
                bet_value = st.number_input(
                    "Your bet for next round ($)",
                    min_value=table_min_bet,
                    max_value=float(table_max_bet) if table_max_bet is not None else None,
                    step=0.01,
                    format="%.2f",
                    value=max(table_min_bet, current_bet if current_bet > 0 else table_min_bet),
                    key=f"blackjack_lan_bet_input_{table_id}_{account}",
                )
                submitted = st.form_submit_button("Set bet")
            if submitted:
                normalized_bet = house_round_charge(float(bet_value))
                valid_limits, limit_errors = _check_game_limits(1, normalized_bet, 1)
                if not valid_limits:
                    for error in limit_errors:
                        if "Buy-in" in error or "buy-in" in error:
                            st.error(error)
                    return
                placed, message = set_blackjack_lan_player_bet(table_id, account, normalized_bet)
                if placed:
                    st.success(message)
                else:
                    st.error(message)
                _fast_rerun()
            ready_count, total_players = blackjack_lan_ready_counts(table_to_view)
            ready_btn_col, ready_count_col = st.columns([4, 1.5])
            with ready_btn_col:
                player_state_for_ready = table_to_view.get("player_states", {}).get(account, {})
                is_ready = bool(player_state_for_ready.get("ready", False))
                ready_label = "Unready" if is_ready else "Ready"
                if st.button(ready_label, key=f"blackjack_lan_ready_{table_id}_{account}", use_container_width=True):
                    changed, message, _auto_started = set_blackjack_lan_player_ready(
                        table_id,
                        account,
                        ready=(not is_ready),
                    )
                    if changed:
                        st.success(message)
                    else:
                        st.error(message)
                    _fast_rerun()
            with ready_count_col:
                st.caption(f"{ready_count}/{total_players} ready")

        render_blackjack_lan_hands(table_to_view, viewer_player=account)

        if (
            (not is_spectator_view)
            and membership == "seated"
            and table_to_view.get("phase") == "player_turns"
        ):
            if current_turn_player == account and player_state.get("status") == "playing":
                hit_col, stand_col = st.columns(2)
                with hit_col:
                    if st.button(
                        "Hit",
                        key=f"blackjack_lan_hit_{table_id}_{account}",
                        use_container_width=True,
                    ):
                        acted, message = blackjack_lan_player_action(table_id, account, "hit")
                        if acted:
                            st.success(message)
                        else:
                            st.error(message)
                        _fast_rerun()
                with stand_col:
                    if st.button(
                        "Stand",
                        key=f"blackjack_lan_stand_{table_id}_{account}",
                        use_container_width=True,
                    ):
                        acted, message = blackjack_lan_player_action(table_id, account, "stand")
                        if acted:
                            st.success(message)
                        else:
                            st.error(message)
                        _fast_rerun()
            else:
                if current_turn_player:
                    st.caption(f"Waiting for {current_turn_player} to act.")
                else:
                    st.caption("Waiting for dealer resolution.")

        if (not is_spectator_view) and membership == "seated" and table_to_view.get("phase") == "finished":
            your_result = player_state.get("result")
            your_message = str(player_state.get("message", "")).strip()
            your_payout = float(player_state.get("payout", 0.0))
            if your_result in {"win", "blackjack"}:
                st.success(your_message or "You won.")
            elif your_result == "push":
                st.info(your_message or "Push.")
            elif your_result == "loss":
                st.error(your_message or "You lost.")
            if your_result is not None:
                st.caption(f"Your payout: ${format_money(your_payout)}")

        with st.expander("Table history"):
            history = table_to_view.get("history", [])
            if not history:
                st.write("No actions yet.")
            else:
                for entry in history[-25:]:
                    st.write(entry)
        return

    if round_state is None:
        current_limits = load_game_limits()
        bet_input = st.number_input(
            "Bet amount ($)",
            min_value=0.01,
            step=0.01,
            format="%.2f",
            key="blackjack_setup_bet",
        )
        bet = house_round_charge(float(bet_input))
        
        # Check game limits (for blackjack, only buy_in limit applies)
        is_valid, limit_errors = _check_game_limits(1, bet, 1, limits=current_limits)  # range=1, guesses=1
        if not is_valid:
            # Only show buy_in limit error for blackjack
            for error in limit_errors:
                if "Buy-in" in error or "buy-in" in error:
                    st.error(error)
        
        setup_confirmed = True
        if is_bet_confirmation_enabled():
            st.caption(f"You are about to bet ${format_money(bet)}.")
            setup_confirmed = st.checkbox("I confirm this bet", key="blackjack_setup_bet_confirm")

        if st.button("Deal cards", key="blackjack_deal_cards", use_container_width=True):
            if is_bet_confirmation_enabled() and not setup_confirmed:
                st.warning("Confirm your bet before dealing.")
                return
            
            # Final validation check before dealing
            is_valid, limit_errors = _check_game_limits(1, bet, 1, limits=current_limits)
            if not is_valid:
                for error in limit_errors:
                    if "Buy-in" in error or "buy-in" in error:
                        st.error(error)
                return
            
            if is_guest_mode:
                if float(st.session_state.get("guest_balance", 0.0)) < float(bet):
                    st.error("Not enough guest funds to cover this bet.")
                    return
            elif not can_afford_account_charge(account, bet):
                st.warning("Insufficient funds. Negative balance is disabled in settings.")
                st.session_state["blackjack_pending_bet"] = float(bet)
                return
            started_round, error = start_blackjack_round(account, bet, is_guest_mode)
            if error:
                st.error(error)
                return
            st.session_state["blackjack_pending_bet"] = None
            st.session_state["blackjack_pending_replay_bet"] = None
            st.session_state["blackjack_round"] = started_round
            _fast_rerun()

        pending_bet = st.session_state.get("blackjack_pending_bet")
        if pending_bet and (not is_guest_mode) and (not is_debt_allowed()):
            if st.button("Enable negative balance and deal cards", key="blackjack_enable_debt_start"):
                st.session_state["setting_allow_negative_balance"] = True
                _persist_ui_settings_for_current_account()
                started_round, error = start_blackjack_round(account, float(pending_bet), False)
                if error:
                    st.error(error)
                    return
                st.session_state["blackjack_pending_bet"] = None
                st.session_state["blackjack_pending_replay_bet"] = None
                st.session_state["blackjack_round"] = started_round
                _fast_rerun()
        return

    player_total = blackjack_hand_total(round_state["player_cards"])
    dealer_total = blackjack_hand_total(round_state["dealer_cards"])
    render_blackjack_analytics_sidebar(round_state, account, is_guest_mode)
    st.write(f"Bet: ${format_money(round_state['bet'])}")
    render_blackjack_table(round_state)
    round_state["animate_player_indexes"] = []
    round_state["animate_dealer_indexes"] = []

    if round_state["status"] == "player_turn":
        if len(round_state["dealer_cards"]) > 1:
            dealer_up_total = blackjack_hand_total(round_state["dealer_cards"][1:])
            st.caption(f"Dealer showing: {dealer_up_total}+")
        st.caption(f"Your total: {player_total}")

        hit_col, stand_col = st.columns(2)
        with hit_col:
            if st.button("Hit", key="blackjack_hit", use_container_width=True):
                round_state["player_cards"].append(blackjack_draw_card(round_state))
                round_state["animate_player_indexes"] = [len(round_state["player_cards"]) - 1]
                round_state["animate_dealer_indexes"] = []
                latest_card = round_state["player_cards"][-1]
                round_state.setdefault("history", []).append(
                    f"You hit and drew {blackjack_format_hand([latest_card])}."
                )
                updated_total = blackjack_hand_total(round_state["player_cards"])
                if updated_total > 21:
                    error = settle_blackjack_round(
                        account,
                        round_state,
                        "loss",
                        f"You busted with {updated_total}. You lose this round.",
                        is_guest_mode,
                    )
                    if error:
                        st.error(error)
                        return
                elif updated_total == 21:
                    error = run_blackjack_dealer_turn(account, round_state, is_guest_mode)
                    if error:
                        st.error(error)
                        return
                _fast_rerun()
        with stand_col:
            if st.button("Stand", key="blackjack_stand", use_container_width=True):
                round_state.setdefault("history", []).append("You stood.")
                error = run_blackjack_dealer_turn(account, round_state, is_guest_mode)
                if error:
                    st.error(error)
                    return
                _fast_rerun()
        return

    st.caption(f"Dealer total: {dealer_total} | Your total: {player_total}")

    result = round_state.get("result")
    message = round_state.get("message", "")
    if result in {"win", "blackjack"}:
        st.success(message)
    elif result == "push":
        st.info(message)
    else:
        st.error(message)
    st.caption(f"Payout credited: ${format_money(round_state.get('payout', 0.0))}")

    replay_col, reset_col = st.columns(2)
    with replay_col:
        if st.button("Play again (same bet)", key="blackjack_same_bet", use_container_width=True):
            replay_bet = float(round_state["bet"])
            if is_guest_mode:
                if float(st.session_state.get("guest_balance", 0.0)) < replay_bet:
                    st.error("Not enough guest funds to play another round.")
                    return
            elif not can_afford_account_charge(account, replay_bet):
                st.warning("Insufficient funds. Negative balance is disabled in settings.")
                st.session_state["blackjack_pending_replay_bet"] = replay_bet
                return
            started_round, error = start_blackjack_round(account, replay_bet, is_guest_mode)
            if error:
                st.error(error)
                return
            st.session_state["blackjack_pending_bet"] = None
            st.session_state["blackjack_pending_replay_bet"] = None
            st.session_state["blackjack_round"] = started_round
            _fast_rerun()
    with reset_col:
        if st.button("Change bet", key="blackjack_change_bet", use_container_width=True):
            st.session_state["blackjack_pending_bet"] = None
            st.session_state["blackjack_pending_replay_bet"] = None
            st.session_state["blackjack_round"] = None
            _fast_rerun()

    pending_replay_bet = st.session_state.get("blackjack_pending_replay_bet")
    if pending_replay_bet and (not is_guest_mode) and (not is_debt_allowed()):
        if st.button("Enable negative balance and replay", key="blackjack_enable_debt_replay"):
            st.session_state["setting_allow_negative_balance"] = True
            _persist_ui_settings_for_current_account()
            started_round, error = start_blackjack_round(account, float(pending_replay_bet), False)
            if error:
                st.error(error)
                return
            st.session_state["blackjack_pending_bet"] = None
            st.session_state["blackjack_pending_replay_bet"] = None
            st.session_state["blackjack_round"] = started_round
            _fast_rerun()


def developer_ui():
    if not is_admin_user():
        st.error("Only the admin account can access this option.")
        return

    st.subheader("Guessing Game Odds")
    current_odds = st.session_state.get("odds", 1.0)
    with st.form("admin_odds_form"):
        new_odds = st.number_input("New guessing game odds multiplier (> 0)", min_value=0.01, value=current_odds, step=0.01)
        submitted = st.form_submit_button("Save guessing game odds")
    if not submitted:
        return
    save_odds(float(new_odds))
    st.session_state["odds"] = float(new_odds)
    st.success("Guessing game odds updated.")


def game_limits_ui():
    if not can_create_admins():
        st.error("Only isaac can access this option.")
        return

    st.subheader("Configure Game Limits")
    st.caption("Set maximum values for game parameters. Leave empty to disable a limit.")
    
    current_limits = load_game_limits()
    
    with st.form("game_limits_form"):
        st.markdown("#### Range")
        enable_range_limit = st.checkbox(
            "Set maximum range",
            value=current_limits["max_range"] is not None,
            key="enable_range_limit"
        )
        if enable_range_limit:
            max_range = st.number_input(
                "Maximum range value",
                min_value=1,
                value=current_limits["max_range"] if current_limits["max_range"] else 1000,
                step=1,
                key="max_range_input"
            )
        else:
            max_range = None
        
        st.markdown("#### Buy-in")
        enable_buyin_limit = st.checkbox(
            "Set maximum buy-in",
            value=current_limits["max_buy_in"] is not None,
            key="enable_buyin_limit"
        )
        if enable_buyin_limit:
            max_buy_in = st.number_input(
                "Maximum buy-in amount ($)",
                min_value=0.01,
                value=current_limits["max_buy_in"] if current_limits["max_buy_in"] else 1000.0,
                step=0.01,
                format="%.2f",
                key="max_buyin_input"
            )
        else:
            max_buy_in = None
        
        st.markdown("#### Guesses")
        enable_guesses_limit = st.checkbox(
            "Set maximum guesses",
            value=current_limits["max_guesses"] is not None,
            key="enable_guesses_limit"
        )
        if enable_guesses_limit:
            max_guesses = st.number_input(
                "Maximum guesses allowed",
                min_value=1,
                value=current_limits["max_guesses"] if current_limits["max_guesses"] else 100,
                step=1,
                key="max_guesses_input"
            )
        else:
            max_guesses = None
        
        submitted = st.form_submit_button("Save game limits")
    
    if not submitted:
        return
    
    save_game_limits(max_range, max_buy_in, max_guesses)
    st.success("Game limits updated.")


def blackjack_lan_admin_ui():
    if not is_admin_user():
        st.error("Only the admin account can access this option.")
        return

    st.subheader("Multiplayer Blackjack Table Controls")
    settings = get_blackjack_lan_settings()
    tables = get_blackjack_lan_tables()

    st.markdown("#### Global Timeout / Penalty")
    with st.form("blackjack_lan_global_settings_form"):
        timeout_seconds = st.number_input(
            "Seconds each player has to decide",
            min_value=5,
            max_value=300,
            value=int(settings.get("turn_timeout_seconds", 30)),
            step=1,
        )
        timeout_penalty = st.number_input(
            "Timeout penalty (% of player bet)",
            min_value=0.0,
            max_value=100.0,
            value=float(settings.get("timeout_penalty_percent", 25.0)),
            step=1.0,
            format="%.1f",
        )
        allow_spectators_default = st.checkbox(
            "Allow spectating by default",
            value=bool(settings.get("allow_spectators_by_default", True)),
        )
        global_submitted = st.form_submit_button("Save timeout settings")
    if global_submitted:
        ok, message = update_blackjack_lan_global_settings(
            timeout_seconds,
            timeout_penalty,
            allow_spectators_default,
        )
        if ok:
            st.success(message)
        else:
            st.error(message)
        _fast_rerun()

    st.markdown("#### Existing Tables")
    if not tables:
        st.info("No tables found.")
        return

    for table in tables:
        table_id = int(table.get("id", 0))
        players = table.get("players", [])
        max_players = int(table.get("max_players", 5))
        min_bet = float(table.get("min_bet", 0.01))
        max_bet = table.get("max_bet")
        phase_label = blackjack_lan_phase_label(table.get("phase"))
        allow_spectators = bool(table.get("allow_spectators", True))
        spectators_require_password = bool(table.get("spectators_require_password", False))
        is_private = bool(table.get("is_private", False))
        st.markdown(
            f"**Table {table_id}** | {len(players)}/{max_players} players | {phase_label} | "
            f"Min bet ${format_money(min_bet)} | "
            + (
                f"Max bet ${format_money(float(max_bet))}"
                if max_bet is not None
                else "Max bet: none"
            )
            + (" | Spectate: on" if allow_spectators else " | Spectate: off")
            + (" | Spectator password: on" if spectators_require_password else " | Spectator password: off")
            + (" | Private" if is_private else " | Public")
        )

        with st.form(f"blackjack_lan_edit_table_{table_id}"):
            edit_max_players = st.number_input(
                f"Table {table_id} max players",
                min_value=1,
                max_value=8,
                value=max_players,
                step=1,
            )
            edit_min_bet = st.number_input(
                f"Table {table_id} min bet ($)",
                min_value=0.01,
                value=min_bet,
                step=0.01,
                format="%.2f",
            )
            edit_has_max = st.checkbox(
                "Set max bet",
                value=max_bet is not None,
                key=f"blackjack_lan_edit_has_max_{table_id}",
            )
            if edit_has_max:
                max_default = float(max_bet) if max_bet is not None else max(edit_min_bet, 10.0)
                edit_max_bet = st.number_input(
                    f"Table {table_id} max bet ($)",
                    min_value=float(edit_min_bet),
                    value=max_default,
                    step=0.01,
                    format="%.2f",
                )
            else:
                edit_max_bet = None
            edit_allow_spectators = st.checkbox(
                "Allow spectators",
                value=allow_spectators,
                key=f"blackjack_lan_edit_allow_spectators_{table_id}",
            )
            edit_spectator_password_required = st.checkbox(
                "Spectators must enter table password",
                value=spectators_require_password,
                key=f"blackjack_lan_edit_spectator_password_required_{table_id}",
            )
            edit_private = st.checkbox(
                "Private table (password protected)",
                value=is_private,
                key=f"blackjack_lan_edit_private_{table_id}",
            )
            if edit_private or edit_spectator_password_required:
                edit_password = st.text_input(
                    "Table password",
                    type="password",
                    key=f"blackjack_lan_edit_password_{table_id}",
                )
            else:
                edit_password = ""
            save_table = st.form_submit_button("Save table settings")
        if save_table:
            ok, message = update_blackjack_lan_table_settings(
                table_id,
                int(edit_max_players),
                house_round_charge(float(edit_min_bet)),
                house_round_charge(float(edit_max_bet)) if edit_max_bet is not None else None,
                edit_allow_spectators,
                edit_spectator_password_required,
                edit_private,
                edit_password,
            )
            if ok:
                st.success(message)
            else:
                st.error(message)
            _fast_rerun()

        if st.button(
            f"Delete table {table_id}",
            key=f"blackjack_lan_delete_table_{table_id}",
            use_container_width=True,
        ):
            ok, message = delete_blackjack_lan_table(table_id)
            if ok:
                st.success(message)
            else:
                st.error(message)
            _fast_rerun()

        st.markdown("---")


def admin_account_tools_ui():
    if not is_admin_user():
        st.error("Only the admin account can access this option.")
        return

    st.subheader("Account tools")
    accounts = list_account_names()
    if not accounts:
        st.info("No accounts available.")
        return

    selected_account = st.selectbox(
        "Choose account",
        accounts,
        key="admin_selected_account",
        index=None,
        placeholder="Select an account",
    )
    if selected_account is None:
        st.info("Select an account to manage.")
        return

    selected_value = get_account_value(selected_account)
    if selected_value is None:
        st.error("Selected account was not found.")
        return

    st.markdown("#### 1) Change Account Value")
    with st.form("admin_change_value_form"):
        st.caption(f"Current balance for {selected_account}: ${format_money(selected_value)}")
        new_balance = st.number_input("New balance ($)", value=float(selected_value), step=1.0, format="%.2f")
        submitted = st.form_submit_button("Save new balance")

    if submitted:
        success, saved_balance = set_account_value(selected_account, new_balance)
        if not success:
            st.error("Failed to update account value.")
        else:
            st.success(f"Updated {selected_account} balance to ${format_money(saved_balance)}.")

    st.markdown("#### 2) View Account Password")
    with st.form("admin_view_password_form"):
        view_submitted = st.form_submit_button("Show password")
    if view_submitted:
        password = get_account_password(selected_account)
        if password is None:
            st.error("Account not found.")
        elif password == "":
            st.info(f"{selected_account} has no password set.")
        else:
            st.code(password)

    st.markdown("#### 3) Delete Account")
    with st.form("admin_delete_account_form"):
        confirm_name = st.text_input("Type account name to confirm delete")
        delete_submitted = st.form_submit_button("Delete account")
    if delete_submitted:
        if confirm_name.strip() != selected_account:
            st.error("Confirmation name does not match selected account.")
        elif not delete_account(selected_account):
            st.error("Failed to delete account.")
        else:
            if st.session_state.get("current_account") == selected_account:
                _sign_out_current_account()
                st.success(f"Deleted account {selected_account}. You were signed out.")
                _fast_rerun()
            st.success(f"Deleted account {selected_account}.")
            _fast_rerun()

    st.markdown("#### 4) Change Account Password")
    with st.form("admin_change_password_form"):
        new_password = st.text_input("New password", type="password", key="admin_new_password")
        confirm_password = st.text_input("Confirm new password", type="password", key="admin_confirm_password")
        change_password_submitted = st.form_submit_button("Save new password")
    if change_password_submitted:
        if not new_password:
            st.error("New password is required.")
        elif new_password != confirm_password:
            st.error("New password confirmation does not match.")
        elif not set_account_password(selected_account, new_password):
            st.error("Failed to update account password.")
        else:
            st.success(f"Updated password for {selected_account}.")

    st.markdown("#### 5) Reset Account Password")
    with st.form("admin_reset_password_form"):
        reset_confirm = st.text_input("Type RESET to confirm password reset")
        reset_password_submitted = st.form_submit_button("Reset password")
    if reset_password_submitted:
        if reset_confirm.strip().upper() != "RESET":
            st.error("Password reset not confirmed.")
        elif not set_account_password(selected_account, ""):
            st.error("Failed to reset account password.")
        else:
            st.success(
                f"Password reset for {selected_account}. "
                "They will be prompted to create a new password at next sign in."
            )

    st.markdown("#### 6) Admin Access")
    if can_create_admins():
        current_admin_status = selected_account == ADMIN_ACCOUNT_NAME or bool(get_account_admin_status(selected_account))
        with st.form("admin_set_admin_form"):
            st.caption(
                "Admins created by isaac get all admin tools, but cannot create new admins."
            )
            admin_access_enabled = st.toggle(
                "Make this account an admin",
                value=current_admin_status,
            )
            save_admin_submitted = st.form_submit_button("Save admin access")
        if save_admin_submitted:
            if selected_account == ADMIN_ACCOUNT_NAME and not admin_access_enabled:
                st.error("isaac must remain an admin.")
            else:
                target_admin_status = bool(admin_access_enabled)
                if selected_account == ADMIN_ACCOUNT_NAME:
                    target_admin_status = True
                if not set_account_admin_status(selected_account, target_admin_status):
                    st.error("Failed to update admin access.")
                elif target_admin_status:
                    st.success(f"{selected_account} can now access admin tools.")
                else:
                    st.success(f"{selected_account} no longer has admin access.")
    else:
        st.info("Only isaac can grant or remove admin access.")


def home_ui():
    st.subheader("Home")
    storage_unavailable = bool(st.session_state.get("storage_unavailable", False))
    completion_message = st.session_state.get("guest_completion_message")
    if completion_message:
        st.success(completion_message)
        st.session_state["guest_completion_message"] = None

    def _activate_home_action(action, reset_guest_setup=False, reset_selected_mode=False):
        st.session_state["active_action"] = action
        if reset_guest_setup:
            st.session_state["guest_mode_setup"] = False
            st.session_state["blackjack_guest_mode_setup"] = False
        if reset_selected_mode:
            st.session_state["selected_game_mode"] = None
        _fast_rerun()

    def _home_action_button(
        label,
        action,
        button_key,
        card_key,
        reset_guest_setup=False,
        reset_selected_mode=False,
        disabled=False,
    ):
        with st.container(key=card_key):
            if st.button(label, key=button_key, use_container_width=True, disabled=disabled):
                _activate_home_action(
                    action,
                    reset_guest_setup=reset_guest_setup,
                    reset_selected_mode=reset_selected_mode,
                )

    games_col, account_col = st.columns(2)
    with games_col:
        st.caption("Games")
        _home_action_button(
            "Number guessing games",
            "Play game",
            "home_play_game",
            "home_card_play_game",
            reset_guest_setup=True,
            reset_selected_mode=True,
        )
        _home_action_button(
            "Blackjack",
            "Blackjack",
            "home_blackjack",
            "home_card_blackjack",
            reset_guest_setup=True,
        )
        _home_action_button(
            "Leaderboards",
            "Leaderboards",
            "home_leaderboards",
            "home_card_leaderboards",
            disabled=storage_unavailable,
        )
    with account_col:
        st.caption("Account & Tools")
        _home_action_button(
            "Add/withdraw money",
            "Add/withdraw money",
            "home_add_withdraw",
            "home_card_add_withdraw",
            disabled=storage_unavailable,
        )
        _home_action_button(
            "Look up account",
            "Look up account",
            "home_lookup",
            "home_card_lookup",
            disabled=storage_unavailable,
        )
        _home_action_button(
            "Calculate odds",
            "Calculate odds",
            "home_calc_odds",
            "home_card_calc_odds",
        )

    if is_admin_user():
        st.markdown("---")
        st.subheader("Admin tools")
        admin_row1_col1, admin_row1_col2 = st.columns(2)
        with admin_row1_col1:
            _home_action_button(
                "House odds",
                "House odds",
                "home_admin_odds",
                "home_card_admin_odds",
            )
        with admin_row1_col2:
            _home_action_button(
                "Account tools",
                "Account tools",
                "home_admin_account_tools",
                "home_card_admin_accounts",
            )
        admin_row2_col1, _admin_row2_col2 = st.columns(2)
        with admin_row2_col1:
            if can_create_admins():
                _home_action_button(
                    "Game limits",
                    "Game limits",
                    "home_admin_game_limits",
                    "home_card_admin_game_limits",
                )
            else:
                _home_action_button(
                    "Game limits (Owner)",
                    "Home",
                    "home_admin_game_limits_disabled",
                    "home_card_admin_game_limits_disabled",
                    disabled=True,
                )


def main():
    st.set_page_config(
        page_title="GAMBLY",
        page_icon="🪙",
        initial_sidebar_state="expanded",
    )
    init_state()
    _enforce_account_session_ownership()
    sync_ui_settings_for_active_account()
    autosave_ui_settings_for_current_account()
    apply_theme()
    _render_account_session_notice()
    _render_storage_unavailable_notice()
    if st.session_state.get("storage_unavailable", False) and st.session_state.get("current_account"):
        _sign_out_current_account(
            session_notice="Account storage is temporarily unavailable. You were signed out. Guest mode is still available."
        )
        _fast_rerun(force=True)
        return
    if (
        st.session_state.get("guest_mode_active", False)
        and st.session_state.get("active_action") not in {"Play game", "Blackjack"}
    ):
        end_guest_session(set_completion_message=True)
    if st.session_state["redirect_to_home"]:
        st.session_state["active_action"] = "Home"
        st.session_state["redirect_to_home"] = False
    allowed_actions = {
        "Home",
        "Look up account",
        "Add/withdraw money",
        "Calculate odds",
        "Play game",
        "Blackjack",
        "Change profile picture",
        "Change password",
        "Leaderboards",
    }
    if st.session_state.get("storage_unavailable", False):
        allowed_actions -= {
            "Look up account",
            "Add/withdraw money",
            "Change profile picture",
            "Change password",
            "Leaderboards",
            "House odds",
            "Game limits",
            "Account tools",
        }
        st.session_state["show_auth_flow"] = False
        st.session_state["auth_flow_mode"] = None
    if is_admin_user():
        allowed_actions.update({"House odds", "Account tools"})
        if can_create_admins():
            allowed_actions.add("Game limits")
    if st.session_state.get("active_action") not in allowed_actions:
        st.session_state["active_action"] = "Home"
    _auto_remove_lan_player_when_not_in_blackjack()
    if st.session_state.get("active_action") == "Home":
        render_header()
    if (
        st.session_state.get("active_action") == "Home"
        and st.session_state.get("current_account") is not None
        and not st.session_state.get("show_auth_flow")
    ):
        render_home_analytics_sidebar(st.session_state["current_account"])
    render_top_controls()
    render_back_button()

    if st.session_state["show_auth_flow"]:
        auth_ui()
    elif st.session_state["active_action"] == "Home":
        home_ui()

    if st.session_state["show_auth_flow"]:
        return

    if st.session_state["active_action"] == "Look up account":
        lookup_account_ui()
    elif st.session_state["active_action"] == "Add/withdraw money":
        add_withdraw_ui()
    elif st.session_state["active_action"] == "Calculate odds":
        odds_calculator_ui()
    elif st.session_state["active_action"] == "Change profile picture":
        change_profile_picture_ui()
    elif st.session_state["active_action"] == "Change password":
        change_password_ui()
    elif st.session_state["active_action"] == "Leaderboards":
        leaderboards_ui()
    elif st.session_state["active_action"] == "Play game":
        play_game_ui()
    elif st.session_state["active_action"] == "Blackjack":
        blackjack_ui()
    elif st.session_state["active_action"] == "House odds":
        developer_ui()
    elif st.session_state["active_action"] == "Game limits":
        game_limits_ui()
    elif st.session_state["active_action"] == "Account tools":
        admin_account_tools_ui()


if __name__ == "__main__":
    main()
    storage_unavailable = bool(st.session_state.get("storage_unavailable", False))
