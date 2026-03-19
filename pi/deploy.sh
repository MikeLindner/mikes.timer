#!/bin/bash
# DuoClock Pi deployment now lives in the bm_clockradio repository.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SIBLING_DEPLOY="$(cd "$SCRIPT_DIR/../../bm_clockradio" 2>/dev/null && pwd)/deploy.sh"

echo "This deploy entrypoint moved to bm_clockradio."

if [ -x "$SIBLING_DEPLOY" ]; then
	echo "Forwarding to: $SIBLING_DEPLOY"
	exec "$SIBLING_DEPLOY" "$@"
fi

echo "Could not find executable sibling deploy script at ../../bm_clockradio/deploy.sh"
echo "Run bm_clockradio/deploy.sh directly from that repository."
exit 1
