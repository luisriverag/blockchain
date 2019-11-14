#!/bin/bash
#
# NAME
#   Parity Wrapper
#
# SYNOPSIS
#   parity_wrapper.sh [-r] [role] [-a] [address] [-p] [arguments]
#
# DESCRIPTION
#   A wrapper for the actual Parity client to make the Docker image easy usable by preparing the Parity client for
#   a set of predefined list of roles the client can take without have to write lines of arguments on run Docker.
#
# OPTIONS
#   -r [--role]         Role the Parity client should use.
#                       Depending on the chosen role Parity gets prepared for that role.
#                       Selecting a specific role can require further arguments.
#                       Checkout ROLES for further information.
#
#   -a [--address]      The Ethereum address that parity should use.
#                       Depending on the chosen role, the address gets inserted at the right
#                       place of the configuration, so Parity is aware of it.
#                       Gets ignored if not necessary for the chosen role.
#
#   -p [--parity-args]  Additional arguments that should be forwarded to the Parity client.
#                       Make sure this is the last argument, cause everything after is
#                       forwarded to Parity.
#
# ROLES
#   The list of available roles is:
#
#   observer
#     - Is the default role
#     - Does only watch for propagated blocks.
#     - Non arguments required at all.
#
#   participant
#     - Connects to an account to being able to create transactions.
#     - Requires the address argument.
#     - Needs the password file and the key-set. (see FILES)
#
#   validator
#     - Connect as authority to the network for validating blocks.
#     - Requires the address argument.
#     - Needs the password file and the key-set. (see FILES)
#
# FILES
#   The configuration folder for Parity takes place at /home/parity/.local/share/io.parity.ethereum.
#   Alternately the shorthand symbolic link at /config can be used.
#   Parity's data base is at /home/parity/.local/share/io.parity.ethereum/chains or available trough /data as well.
#   To provide custom files in addition bind a volume through Docker to the sub-folder called 'custom'.
#   The password file is expected to be placed in the custom configuration folder names 'pass.pwd'.
#   The key-set is expected to to be placed in the custom configuration folder under 'keys/Trustlines/'
#   Besides from using the pre-defined locations, it is possible to define them manually thought the parity
#   arguments. Checkout their documentation to do so.
#

set -e

# Adjustable configuration values.
ROLE="observer"
ADDRESS=""
PARITY_ARGS_ARRAY=()

# Internal stuff.
declare -a VALID_ROLE_LIST=(
  observer
  participant
  validator
)
SHARED_VOLUME_PATH="/shared/"

# Make sure some environment variables are defined.
[[ -z "$PARITY_BIN" ]] && PARITY_BIN=/usr/local/bin/parity
[[ -z "$PARITY_CONFIG_DIR" ]] &&
  PARITY_CONFIG_DIR=/home/parity/.local/share/io.parity.ethereum
PARITY_CONFIG_FILE="${PARITY_CONFIG_DIR}/config.toml"

function showVersion() {
  if [[ -e /VERSION ]]; then
    echo "Version: $(cat /VERSION)"
  fi
}

# Print the header of this script as help.
# The header ends with the first empty line.
#
function printHelp() {
  local file="${BASH_SOURCE[0]}"
  sed -e '/^$/,$d; s/^#//; s/^\!\/bin\/bash//' "$file"
}

# Check if the defined role for the client is valid.
# Use a list of predefined roles to check for.
# In case the selected role is invalid, it prints our the error message and exits.
#
function checkRoleArgument() {
  # Check each known role and end if it match.
  for i in "${VALID_ROLE_LIST[@]}"; do
    [[ $i == "$ROLE" ]] && return
  done

  # Error report to the user with the correct usage.
  echo "The defined role ('$ROLE') is invalid."
  echo "Please choose one of the following values: ${VALID_ROLE_LIST[*]}"
  exit 1
}

# Check if the set address is a valid address
# Does not do a checksum test
#
function checkAddressArgument() {
  [[ $ADDRESS =~ ^0x[0-9a-fA-F]{40}$ ]] && return

  # Error report to the user with the correct usage.
  echo "The defined address ('$ADDRESS') is invalid."
  exit 1
}

# Parse the arguments, given to the script by the caller.
# Not defined configuration values stay with their default values.
# A not known argument leads to an exit with status code 1.
#
# Arguments:
#   $1 - all arguments by the caller
#
function parseArguments() {
  while [[ $# -gt 0 ]]; do
    arg="$1"

    # Print help and exit if requested.
    if [[ $arg == --help ]] || [[ $arg == -h ]]; then
      printHelp
      exit 0

    # Define the role for the client.
    elif [[ $arg == --role ]] || [[ $arg == -r ]]; then
      ROLE="$2"
      checkRoleArgument # Make sure to have a valid role.
      shift             # arg
      shift             # value

    # Define the address to bind.
    elif [[ $arg == --address ]] || [[ $arg == -a ]]; then
      # Take the next argument as the address and jump other it.
      ADDRESS="$2"
      checkAddressArgument # Make sure to have a valid address.
      shift                # arg
      shift                # value

    # Additional arguments for the Parity client.
    # Use all remain arguments for parity.
    elif [[ $arg == --parity-args ]] || [[ $arg == -p ]]; then
      shift # arg
      PARITY_ARGS_ARRAY=("$@")
      break

    # A not known argument.
    else
      echo "Unknown argument: $arg"
      exit 1
    fi
  done
}

# Replace a option value for the parity configuration file.
# The file is determined by the $PARITY_CONFIG_FILE variable.
# The change of the file happens in place.
#
# Developer:
#   This function makes a bunch of assumption how the configuration lines
#   look like. Take a look into the included comments, if it still fits
#   the use-case.
#
# Arguments:
#   $1 - key name
#   $2 - value
#   $3 - placeholder (optional ["0xAddress"])
#
function replace_configuration_placeholder() {
  key_name="$1"
  value="$2"
  placeholder="$3"
  [[ -z "$placeholder" ]] && placeholder="0xAddress"

  # Spaces could exist in-between.
  # The placeholder/value are quoted.
  # The placeholder/value could be within a list.
  # Anything could follow afterwards (comment).
  sed -i -e "s/^\(${key_name}\ *=\ *\[\?\"\)${placeholder}\(\"\]\?.*$\)/\1${value}\2/" \
    "$PARITY_CONFIG_FILE"
}

# Adjust the configuration file for parity for the selected role.
# Includes some checks of the arguments constellation and hints for the user.
# Use the predefined configuration snippets filled with the users input.
#
function adjustConfiguration() {
  # Make sure an address is given if needed.
  if { [[ $ROLE == 'participant' ]] || [[ $ROLE == 'validator' ]]; } && [[ -z "$ADDRESS" ]]; then
    echo "Missing or empty address but required by selected role!"
    echo "Make sure the argument order is correct (parity arguments at the end)."
    exit 1
  fi

  # Copy base config file
  cp "${PARITY_CONFIG_DIR}/base.toml" ${PARITY_CONFIG_FILE}
  {
    # Append the correct configuration template for the selected role.
    cat "${PARITY_CONFIG_DIR}/${ROLE}-role.toml"
    # Append docker specific config
    cat "${PARITY_CONFIG_DIR}/docker.toml"
    # Append chainspecific config
    cat "${PARITY_CONFIG_DIR}/chain.toml"
  } >>${PARITY_CONFIG_FILE}

  # Handle the different roles.
  # Append the respective configuration snippet with the necessary variable to the default configuration file.
  case $ROLE in
  "validator")
    echo "Run as validator with account ${ADDRESS}"
    replace_configuration_placeholder "engine_signer" "$ADDRESS"
    ;;

  "participant")
    echo "Run as participant with unlocked account ${ADDRESS}"
    replace_configuration_placeholder "unlock" "$ADDRESS"
    ;;

  "observer")
    echo "Run as observer without an account."
    ;;
  esac
}

# Caller of the actual Parity client binaries.
# The provided arguments by the user gets forwarded.
#
function runParity() {
  printf "\nStart Parity"
  number_parity_args=${#PARITY_ARGS_ARRAY[@]}
  [[ $number_parity_args -gt 0 ]] && printf " with the additional %d arguments: %-s" "$number_parity_args" "${PARITY_ARGS_ARRAY[*]}"
  printf "\n"

  exec $PARITY_BIN "${PARITY_ARGS_ARRAY[@]}"
}

function copySpecFileToSharedVolume() {
  if [[ -d "$SHARED_VOLUME_PATH" ]]; then
    echo "Copying chain spec file to shared volume"
    cp /config/trustlines-spec.json "$SHARED_VOLUME_PATH/trustlines-spec.json"
  else
    echo "Shared volume apparently not mounted, skip copying chain spec file"
  fi
}

# Getting Started
showVersion
parseArguments "$@"
adjustConfiguration
copySpecFileToSharedVolume
runParity
