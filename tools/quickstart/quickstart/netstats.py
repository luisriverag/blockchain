from pathlib import Path
from textwrap import fill

import click
import requests

from quickstart.constants import NETSTATS_ENV_FILE_PATH, NETSTATS_SERVER_BASE_URL
from quickstart.utils import is_netstats_prepared

ENV_FILE_TEMPLATE = """\
WS_USER={username}
WS_PASSWORD={password}
INSTANCE_NAME={instance_name}
# HIDE_VALIDATOR_STATUS=false
"""


def setup_interactively() -> None:
    if is_netstats_prepared():
        click.echo("You have already set up the netstats client.\n")
        return

    click.echo(
        "\n".join(
            (
                "We can set up a client that reports to the netstats server running at",
                NETSTATS_SERVER_BASE_URL,
                "This helps the community to observe the state of the network.",
                "",
                "You will need credentials to do that. Write a mail to",
                "'netstats@trustlines.foundation'",
                "to receive some.",
                "",
            )
        )
    )

    if not click.confirm(
        fill(
            "Have you already received credentials and do you want to set the netstats client up?"
        )
    ):
        # Necessary to make docker-compose not complaining about it.
        Path(NETSTATS_ENV_FILE_PATH).touch()
        return

    while True:
        username = click.prompt("Username")
        password = click.prompt("Password", hide_input=True)

        if check_credentials(username, password):
            click.echo("The provided credentials are valid.")
            break

        else:
            click.echo(
                "\n"
                + "\n".join(
                    (
                        "The provided credentials could not be verified.",
                        "Please try entering them and make sure you are connected to the internet.",
                    )
                )
            )

    click.echo(
        "\n".join(
            (
                "Please enter a name to identify your instance on the website.",
                "You are free to choose any name you like. Note that the name will be publicly visible.",
            )
        )
    )

    instance_name = click.prompt("Instance name")

    with open(NETSTATS_ENV_FILE_PATH, "w") as env_file:
        env_file.write(
            ENV_FILE_TEMPLATE.format(
                username=username, password=password, instance_name=instance_name
            )
        )

    click.echo("Netstats client setup complete.\n")


def check_credentials(username: str, password: str) -> bool:
    url = f"{NETSTATS_SERVER_BASE_URL}/check"
    response = requests.get(url, auth=(username, password), timeout=10.0)
    return response.status_code == 200
