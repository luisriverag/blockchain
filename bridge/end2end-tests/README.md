# Bridge end2end tests

This directory contains the end2end tests of the Trustlines Blockchain Bridge (tlbc-bridge).

## Requirements

To run the end2end tests you need to have the tlbc-bridge
installed in your environment. This will be automatically done if using `make`.
Additionally Openethereum must be installed.

## Run

To run the end2end tests, use
`make test-end2end`
from the `bridge` directory, or use `make test-end2end/bridge`
from the blockchain root directory.

## Run without make

To run the tests without `make`, make sure that tlbc-bridge and Openethereum
are installed. Then run `pytest bridge/end2end-tests/tests`.

## Test Structure

The end2end tests start all relevant parts of the bridge in separate processes in the background.
It will check that every service is ready (can be defined for every service separatly) before starting the end2end tests.
A strong emphasis is on making the tests reliable, but also fast. This should be done by not using bare `sleeps`,
but instead poll with a timeout.
