import json
import os
import re
import sys
from pathlib import Path
from typing import Tuple

import click
from eth_account import Account

from quickstart.constants import (
    ADDRESS_FILE_PATH,
    BRIDGE_CONFIG_FILE_EXTERNAL,
    KEY_DIR,
    NETSTATS_ENV_FILE_PATH,
    PASSWORD_FILE_PATH,
)


def ensure_clean_setup():
    if os.path.isdir(KEY_DIR):
        raise click.ClickException(
            "The directory holding the keys already exists.\n"
            "This should not occur during normal operation."
        )

    if os.path.isfile(PASSWORD_FILE_PATH):
        raise click.ClickException(
            "The password file already exists.\n"
            "This should not occur during normal operation."
        )


def non_empty_file_exists(file_path: str) -> bool:
    return (
        os.path.isfile(file_path)
        # Ignore touched only files (docker-compose workaround)
        and os.stat(file_path).st_size != 0
    )


def is_validator_account_prepared() -> bool:
    return os.path.isfile(ADDRESS_FILE_PATH)


def is_netstats_prepared() -> bool:
    return non_empty_file_exists(NETSTATS_ENV_FILE_PATH)


def is_bridge_prepared() -> bool:
    return non_empty_file_exists(BRIDGE_CONFIG_FILE_EXTERNAL)


class TrustlinesFiles:
    def __init__(self, password_path, address_path, keystore_path):
        self.password_path = password_path
        self.address_path = address_path
        self.keystore_path = keystore_path

    def store(self, account, password):
        # Instead of just copying the file, we encrypt it again since the
        # file itself may use scrypt as key derivative function which
        # parity can't handle
        json_account = account.encrypt(password, kdf="pbkdf2")

        os.makedirs(os.path.dirname(os.path.abspath(self.keystore_path)), exist_ok=True)
        with open(self.keystore_path, "w") as f:
            f.write(json.dumps(json_account))

        with open(self.password_path, "w") as f:
            f.write(password)

        with open(self.address_path, "w") as f:
            f.write(account.address)


def is_wrong_password_error(err):
    return type(err) is ValueError and str(err) == "MAC mismatch"


def get_keystore_path() -> str:
    click.echo(
        "Please enter the path to the keystore file to import.\nIf you started the "
        "process via the quickstart scipt, please consider that you are running "
        "within a Docker virtual file system. You can access the current working "
        "directory via '/data'. (e.g. './my-dir/keystore.json' becomes "
        "'/data/my-dir/keystore.json')"
    )

    while True:
        raw_path = click.prompt("Path to keystore", default="./account-key.json")
        absolute_path = Path(raw_path).expanduser().absolute()

        if os.path.isfile(absolute_path) and os.access(absolute_path, os.R_OK):
            return str(absolute_path)

        else:
            click.echo(
                "The given path does not exist or is not readable. "
                "Please try entering it again."
            )


def read_private_key() -> str:
    while True:
        private_key = click.prompt(
            "Private key (hex encoded, without 0x prefix)", hide_input=True
        )

        if re.fullmatch("[0-9a-fA-F]{64}", private_key):
            return private_key

        click.echo(
            "The private key must be entered as a hex encoded string. Please try again."
        )


def read_encryption_password() -> str:
    click.echo(f"Please enter a password to encrypt the private key.")

    while True:
        password = click.prompt("Password", hide_input=True)
        password_repeat = click.prompt("Password (repeat)", hide_input=True)

        if password == password_repeat:
            return password

        click.echo("Passwords do not match. Please try again.")


def read_decryption_password(keyfile_dict) -> Tuple[Account, str]:
    click.echo("Please enter the password to decrypt the keystore.")

    while True:
        password = click.prompt("Password", hide_input=True)

        try:
            account = Account.from_key(Account.decrypt(keyfile_dict, password))
            return account, password

        except Exception as err:
            if is_wrong_password_error(err):
                click.echo("The password you entered is wrong. Please try again.")
            else:
                click.echo(f"Error: failed to decrypt keystore file: {repr(err)}")
                sys.exit(1)