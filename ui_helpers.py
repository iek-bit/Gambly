"""CLI UI helpers.

Streamlit UI lives in streamlit_app.py. This module intentionally keeps only
terminal prompts/printing for fallback mode.
"""

USE_OSASCRIPT_UI = False


def set_ui_mode(enabled):
    # Retained for compatibility with existing callers.
    global USE_OSASCRIPT_UI
    USE_OSASCRIPT_UI = bool(enabled)


def is_ui_mode():
    return False


def ui_info(message, title="Number Guessing Game"):
    # CLI fallback only.
    _ = title
    print(message)


def ui_error(message, title="Number Guessing Game"):
    # CLI fallback only.
    _ = title
    print(message)


def choose_from_list(prompt, options, title="Number Guessing Game"):
    # Terminal list picker fallback.
    _ = title
    print(prompt)
    for index, option in enumerate(options, start=1):
        print(f"{index}: {option}")
    while True:
        raw_value = input(f"Choose an option (1-{len(options)}), or press Enter to cancel: ").strip()
        if raw_value == "":
            return None
        try:
            picked_index = int(raw_value)
        except ValueError:
            ui_error("Please enter a whole number.")
            continue
        if 1 <= picked_index <= len(options):
            return options[picked_index - 1]
        ui_error(f"Please enter a number from 1 to {len(options)}.")


def prompt_text(prompt, title="Number Guessing Game", allow_empty=False):
    # Prompt for free text in terminal mode.
    _ = title
    while True:
        value = input(prompt).strip()
        if not value and not allow_empty:
            ui_error("This field cannot be empty.")
            continue
        return value


def prompt_choice(prompt, valid_choices):
    # Keep prompting until one of the allowed choices is entered.
    valid = {choice.lower() for choice in valid_choices}
    while True:
        value = prompt_text(prompt)
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized in valid:
            return normalized
        ui_error(f"Invalid choice. Valid options: {', '.join(valid_choices)}")


def prompt_int(prompt, min_value=None, max_value=None):
    # Prompt for an integer and enforce optional bounds.
    while True:
        raw_value = prompt_text(prompt)
        if raw_value is None:
            return None
        try:
            value = int(raw_value)
        except ValueError:
            ui_error("Please enter a whole number.")
            continue

        if min_value is not None and value < min_value:
            ui_error(f"Please enter a number greater than or equal to {min_value}.")
            continue
        if max_value is not None and value > max_value:
            ui_error(f"Please enter a number less than or equal to {max_value}.")
            continue
        return value


def prompt_float(prompt, min_value=None):
    # Prompt for a float and enforce an optional minimum.
    while True:
        raw_value = prompt_text(prompt)
        if raw_value is None:
            return None
        try:
            value = float(raw_value)
        except ValueError:
            ui_error("Please enter a valid number.")
            continue

        if min_value is not None and value < min_value:
            ui_error(f"Please enter a value greater than or equal to {min_value}.")
            continue
        return value


def add_funds():
    # Prompt for a positive amount to add.
    return prompt_float("How much money would you like to add (in dollars)? ", 0.0)


def add_or_withdraw_funds():
    # Signed amount: positive adds money, negative withdraws money.
    return prompt_float("Enter amount (positive add, negative withdraw): ")


def choose_menu_option(current_account):
    # Legacy API retained for compatibility with old flow.
    _ = current_account
    return None
