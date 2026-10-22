#!/usr/bin/env bash
# Emit the tail of a log file as a GitHub Actions error annotation, so a failed run can be
# diagnosed from the check-run annotations without downloading logs.
# Usage: annotate_log.sh <logfile> <short title without commas/colons>
log="${1:-}"
title="${2:-ci}"
[ -f "$log" ] || exit 0
body=$(tail -n 70 "$log" | tr -d '\r' | sed -e 's/%/%25/g' | awk '{printf "%s%%0A", $0}')
echo "::error title=${title}::${body}"
