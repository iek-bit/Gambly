"""Account creation operations."""

from storage import create_account_record, get_account_value, is_reserved_account_name
from ui_helpers import add_funds, prompt_text, ui_error, ui_info
from money_utils import format_money, house_round_credit


def create_account():
    # Create a new account with an initial deposit.
    account = prompt_text("What would you like your account name to be? ")
    if account is None:
        return
    if is_reserved_account_name(account):
        ui_error("That account name is reserved.")
        return
    if get_account_value(account) is not None:
        ui_error("An account with that name already exists.")
        return

    add_amount = add_funds()
    if add_amount is None:
        return
    add_amount = house_round_credit(add_amount)

    if not create_account_record(account, add_amount):
        ui_error("Failed to create account.")
        return

    ui_info(f"Your account name is {account}, and you have ${format_money(get_account_value(account))}")
