import argparse
import getpass
import sqlite3
import sys

from backend.config import Settings
from backend.database import UserRepository


def read_password() -> str:
    """Read the new password twice, from a terminal or from stdin.

    ``getpass`` blocks forever when stdin is not a terminal, which is how
    ``docker compose exec`` (without ``-t``) runs. Falling back to a plain line
    read lets a deployment provision its first account non-interactively; an
    empty read is rejected by the password policy, so a silent failure stays
    visible instead of creating a blank account.
    """

    if sys.stdin.isatty():
        password = getpass.getpass("Password: ")
        repeated = getpass.getpass("Repeat password: ")
    else:
        password = sys.stdin.readline().rstrip("\n")
        repeated = sys.stdin.readline().rstrip("\n")
    if password != repeated:
        raise ValueError("Passwords do not match")
    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize SQLite or create an auth user")
    parser.add_argument("command", choices=("init", "create"))
    parser.add_argument("login", nargs="?")
    arguments = parser.parse_args()
    repository = UserRepository(Settings.from_env().database)
    repository.initialize()
    if arguments.command == "init":
        print(f"Database initialized: {repository.path}")
        return
    if not arguments.login:
        parser.error("create requires a login")
    try:
        password = read_password()
        user = repository.create(arguments.login, password)
    except (ValueError, sqlite3.IntegrityError) as error:
        parser.error(str(error))
    print(f"User created: {user.login} ({user.id})")


if __name__ == "__main__":
    main()
