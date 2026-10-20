#!/bin/sh
# Creality K1 installer (Guilouz Creality Helper Script layout). Runs on the
# printer itself under busybox sh; only needs cp, sed, grep, unzip.
#
#   ./install-k1.sh install [--restart]   copy the extra + add [include]
#   ./install-k1.sh uninstall [--restart]
#   ./install-k1.sh mainsail /path/mainsail.zip   deploy the patched Mainsail
#   ./install-k1.sh status
#
# Paths follow the helper script's paths.sh; override with env vars (also
# used by the tests): KLIPPER_EXTRAS, PRINTER_DATA, MAINSAIL_DIR, KLIPPY_ENV.
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
KLIPPER_EXTRAS="${KLIPPER_EXTRAS:-/usr/share/klipper/klippy/extras}"
PRINTER_DATA="${PRINTER_DATA:-/usr/data/printer_data}"
MAINSAIL_DIR="${MAINSAIL_DIR:-/usr/data/mainsail}"
KLIPPY_PY="${KLIPPY_PY:-/usr/share/klippy-env/bin/python}"
KLIPPER_INIT="${KLIPPER_INIT:-/etc/init.d/S55klipper_service}"
CFG_DIR="$PRINTER_DATA/config"
INCLUDE_LINE="[include speed_limiter.cfg]"
FILES="speed_limiter.py speed_limiter_core.py"

die() { echo "Error: $*" >&2; exit 1; }

is_printing() {
    state="$( (curl -s http://127.0.0.1:7125/printer/objects/query?print_stats 2>/dev/null \
        || wget -qO- http://127.0.0.1:7125/printer/objects/query?print_stats 2>/dev/null) || true)"
    echo "$state" | grep -q '"state": *"printing"'
}

restart_klipper() {
    if is_printing; then
        die "a print is running; not restarting Klipper. Restart it yourself when done."
    fi
    [ -x "$KLIPPER_INIT" ] || die "$KLIPPER_INIT not found"
    "$KLIPPER_INIT" restart
}

do_install() {
    [ -d "$KLIPPER_EXTRAS" ] || die "Klipper extras not found at $KLIPPER_EXTRAS"
    [ -f "$CFG_DIR/printer.cfg" ] || die "no printer.cfg in $CFG_DIR"
    if [ -x "$KLIPPY_PY" ]; then
        for f in $FILES; do
            "$KLIPPY_PY" -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" \
                "$HERE/klipper/$f" || die "$f does not parse with the printer's Python"
        done
    fi
    for f in $FILES; do
        rm -f "$KLIPPER_EXTRAS/$f" "$KLIPPER_EXTRAS/${f}c"
        cp "$HERE/klipper/$f" "$KLIPPER_EXTRAS/$f"
    done
    if [ ! -f "$CFG_DIR/speed_limiter.cfg" ]; then
        cp "$HERE/printer.cfg.example" "$CFG_DIR/speed_limiter.cfg"
        echo "Created $CFG_DIR/speed_limiter.cfg - set max_volumetric_flow for your hotend."
    fi
    if ! grep -q "^\[include speed_limiter.cfg\]" "$CFG_DIR/printer.cfg"; then
        [ -f "$CFG_DIR/printer.cfg.pre-speed-limiter" ] \
            || cp "$CFG_DIR/printer.cfg" "$CFG_DIR/printer.cfg.pre-speed-limiter"
        # Includes must come before SAVE_CONFIG's auto-generated block
        if grep -q "^#\*# <---------------------- SAVE_CONFIG" "$CFG_DIR/printer.cfg"; then
            awk -v inc="$INCLUDE_LINE" '/^#\*# <---------------------- SAVE_CONFIG/ && !done \
                { print inc; print ""; done=1 } { print }' \
                "$CFG_DIR/printer.cfg" > "$CFG_DIR/printer.cfg.tmp" \
                && mv "$CFG_DIR/printer.cfg.tmp" "$CFG_DIR/printer.cfg"
        else
            printf '\n%s\n' "$INCLUDE_LINE" >> "$CFG_DIR/printer.cfg"
        fi
        echo "Added $INCLUDE_LINE to printer.cfg (backup: printer.cfg.pre-speed-limiter)."
    fi
    echo "Installed. Restart Klipper to activate."
    [ "$1" = "--restart" ] && restart_klipper
    return 0
}

do_uninstall() {
    for f in $FILES; do rm -f "$KLIPPER_EXTRAS/$f" "$KLIPPER_EXTRAS/${f}c"; done
    sed -i "/^\[include speed_limiter.cfg\]/d" "$CFG_DIR/printer.cfg"
    rm -f "$CFG_DIR/speed_limiter.cfg"
    echo "Removed. Restart Klipper to apply."
    [ "$1" = "--restart" ] && restart_klipper
    return 0
}

do_mainsail() {
    zip="$1"
    [ -f "$zip" ] || die "usage: $0 mainsail /path/to/mainsail.zip"
    new="$MAINSAIL_DIR.new"
    rm -rf "$new"; mkdir -p "$new"
    unzip -q "$zip" -d "$new" || { rm -rf "$new"; die "unzip failed"; }
    [ -f "$new/index.html" ] || { rm -rf "$new"; die "zip has no index.html"; }
    rm -f "$new/mainsail.zip"
    rm -rf "$MAINSAIL_DIR.bak"
    [ -d "$MAINSAIL_DIR" ] && mv "$MAINSAIL_DIR" "$MAINSAIL_DIR.bak"
    mv "$new" "$MAINSAIL_DIR"
    echo "Deployed. Previous version kept in $MAINSAIL_DIR.bak. Hard-refresh the browser."
    echo "Updating Mainsail from the UI/Moonraker or re-running the helper script undoes this."
}

do_status() {
    for f in $FILES; do
        [ -f "$KLIPPER_EXTRAS/$f" ] && echo "extra:   $f installed" || echo "extra:   $f MISSING"
    done
    grep -q "^\[include speed_limiter.cfg\]" "$CFG_DIR/printer.cfg" \
        && echo "config:  include present" || echo "config:  include MISSING from printer.cfg"
    [ -d "$MAINSAIL_DIR" ] && grep -rlq "SpeedLimit\|Speed limit" "$MAINSAIL_DIR" 2>/dev/null \
        && echo "mainsail: patched build" || echo "mainsail: not patched (or not found)"
    log="$PRINTER_DATA/logs/klippy.log"
    if [ -f "$log" ]; then
        grep -m1 "Git version" "$log" || true
        grep -m1 "Python:" "$log" || true
        grep "speed_limiter" "$log" | tail -5 || true
    fi
}

cmd="${1:-}"; [ $# -gt 0 ] && shift
case "$cmd" in
    install) do_install "$@" ;;
    uninstall) do_uninstall "$@" ;;
    mainsail) do_mainsail "$@" ;;
    status) do_status ;;
    *) die "usage: $0 install|uninstall|mainsail ZIP|status" ;;
esac
