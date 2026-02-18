"""Authentication and sign-in routing helpers."""

from storage import (
    get_account_password,
    get_account_value,
    is_reserved_account_name,
    set_account_password,
)
from ui_helpers import prompt_text, ui_error, ui_info


def authenticate_or_setup_password(account):
    # During sign-in, set a password if missing, otherwise verify it.
    stored_password = get_account_password(account)
    if stored_password is None:
        ui_error("Account not found.")
        return False

    if stored_password == "":
        ui_info(f"No password is set for '{account}' yet. Create one now.")
        while True:
            password = prompt_text(f"Create a password for '{account}':")
            if password is None:
                return False
            confirm = prompt_text(f"Confirm password for '{account}':")
            if confirm is None:
                return False
            if password != confirm:
                ui_error("Passwords do not match.")
                continue
            if not set_account_password(account, password):
                ui_error("Failed to save password.")
                return False
            ui_info("Password created.")
            return True

    entered_password = prompt_text(f"Enter your password for '{account}':")
    if entered_password is None:
        return False
    if entered_password != stored_password:
        ui_error("Incorrect password.")
        return False
    return True


def require_signed_in(current_account, task_description):
    # Ensure a signed-in account exists; if not, route to sign-in and return the account.
    if current_account is not None:
        return current_account

    ui_error(f"You need to sign in before you can {task_description}.")
    account = prompt_text("What account would you like to sign into?")
    if account is None:
        return None
    if is_reserved_account_name(account):
        ui_error("That account name is reserved.")
        return None

    value = get_account_value(account)
    if value is None:
        ui_error("Account not found.")
        return None
    if not authenticate_or_setup_password(account):
        ui_error("Sign-in failed.")
        return None

    ui_info(f"Signed in as {account}. Returning to your previous task.")
    return account
