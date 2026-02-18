"""Game calculations and play loop."""

from random import randint

from storage import add_account_value, get_account_value, record_game_result
from ui_helpers import (
    choose_from_list,
    is_ui_mode,
    prompt_choice,
    prompt_int,
    ui_error,
    ui_info,
)
from money_utils import format_money, house_round_charge, house_round_credit


# Calculate the payout that gives break-even expected value.
def calculate_payout(num_range, price_per_round, guesses):
    return (num_range * price_per_round) / (2 ** (guesses - 1))


def play_game(account, odds):
    # Run one game session for the signed-in account.
    if get_account_value(account) is None:
        ui_error("Account not found.")
        return

    if is_ui_mode():
        picked_game = choose_from_list(
            "Which game would you like to play?",
            ["1: you guess the number", "2: the computer guesses the number"],
        )
        if picked_game is None:
            return
        game_type = "1" if picked_game.startswith("1:") else "2"
    else:
        print("Which of these games would you like to play?")
        print("1: you guess the number")
        print("2: the computer guesses the number")
        game_type = prompt_choice("Enter choice (1 or 2): ", ["1", "2"])
        if game_type is None:
            return

    if game_type == "1":
        num_range = prompt_int("What would you like the range to be? ", 1)
        if num_range is None:
            return
        price_per_round = prompt_int("What would you like the buy-in to be? ", 0)
        if price_per_round is None:
            return
        guesses = prompt_int("How many guesses would you like to have? ", 1)
        if guesses is None:
            return

        raw_payout = calculate_payout(num_range, price_per_round, guesses) / odds
        payout = max(house_round_credit(raw_payout), float(price_per_round))

        ui_info(f"If you win, you will get ${format_money(payout)}.")
        play = 1

        while play == 1:
            player_guesses = 0
            number = randint(1, num_range)
            win = 0

            add_account_value(account, -price_per_round)

            while win == 0 and player_guesses < guesses:
                guess = prompt_int(
                    f"Guess a number between 1 and {num_range} (including the endpoints): "
                )
                if guess is None:
                    play = 0
                    break

                if guess < 1 or guess > num_range:
                    ui_error(f"Please guess a number from 1 to {num_range}.")
                elif guess == number:
                    ui_info(f"You won ${format_money(payout)}!")
                    add_account_value(account, payout)
                    record_game_result(account, price_per_round, payout, True, "player_guess")
                    win = 1
                elif guess > number:
                    ui_info("Your guess was too high.")
                    player_guesses += 1
                else:
                    ui_info("Your guess was too low.")
                    player_guesses += 1

            if play == 0:
                break

            if win != 1:
                record_game_result(account, price_per_round, 0.0, False, "player_guess")
                ui_info(f"In total, you lost ${format_money(price_per_round)}.")
            else:
                ui_info(f"In total, you made ${format_money(payout - price_per_round)}.")

            if is_ui_mode():
                replay_choice = choose_from_list("Do you want to play again?", ["1: Yes", "2: No"])
                if replay_choice is None or replay_choice.startswith("2:"):
                    play = 0
                else:
                    play = 1
            else:
                print("Do you want to play again?")
                print("1: Yes")
                print("2: No")
                play_choice = prompt_choice("Enter choice (1 or 2): ", ["1", "2"])
                if play_choice == "1":
                    play = 1
                else:
                    play = 0

    elif game_type == "2":
        num_range = prompt_int("What is the maximum number in the range? ", 1)
        if num_range is None:
            return
        secret_number = prompt_int("What is your secret number? ", 1, num_range)
        if secret_number is None:
            return
        guesses = prompt_int("How many guesses does the computer get? ", 1)
        if guesses is None:
            return
        price_per_round = prompt_int("How much does the computer pay you per round? ", 0)
        if price_per_round is None:
            return

        raw_payout = calculate_payout(num_range, price_per_round, guesses) * odds
        payout = max(house_round_charge(raw_payout), float(price_per_round))
        ui_info(f"If the computer wins, you will lose ${format_money(payout)}.")

        play = 1
        while play == 1:
            add_account_value(account, price_per_round)

            low = 1
            high = num_range
            guessed = False

            for attempt in range(1, guesses + 1):
                if guesses == 1:
                    guess = randint(1, num_range)
                elif attempt == guesses:
                    if low > high:
                        break
                    guess = randint(low, high)
                else:
                    if low > high:
                        break
                    guess = (low + high) // 2

                ui_info(f"Computer guess #{attempt}: {guess}")

                if guess == secret_number:
                    ui_info("The computer guessed your number!")
                    add_account_value(account, -payout)
                    guessed = True
                    break
                elif guess < secret_number:
                    ui_info("Too low.")
                    low = guess + 1
                else:
                    ui_info("Too high.")
                    high = guess - 1

                if not is_ui_mode():
                    input("Press Enter to see the computer's next guess...")

            if not guessed:
                ui_info("The computer failed to guess your number.")
                record_game_result(account, 0.0, price_per_round, True, "computer_guess")
            else:
                record_game_result(account, payout, price_per_round, False, "computer_guess")

            if is_ui_mode():
                replay_choice = choose_from_list("Do you want to play again?", ["1: Yes", "2: No"])
                if replay_choice is None or replay_choice.startswith("2:"):
                    play = 0
                else:
                    play = 1
            else:
                print("Do you want to play again?")
                print("1: Yes")
                print("2: No")
                play_choice = prompt_choice("Enter choice (1 or 2): ", ["1", "2"])
                if play_choice == "1":
                    play = 1
                else:
                    play = 0

        ui_info(f"Your final balance is ${format_money(get_account_value(account))}.")

    else:
        ui_error("That is not a valid option.")
