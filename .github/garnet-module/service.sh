#!/system/bin/sh

MODDIR=${0%/*}
LOG="$MODDIR/ath9k_htc.log"

exec >>"$LOG" 2>&1

echo
echo "===== garnet AR9271 loader: $(date) ====="
echo "kernel=$(uname -r)"

EXPECTED_RELEASE="5.10.260-gki-g7ee66f07cebf"
if [ "$(uname -r)" != "$EXPECTED_RELEASE" ]; then
    echo "ERROR: expected $EXPECTED_RELEASE"
    exit 1
fi

COUNT=0
while [ ! -d /sys/module/cfg80211 ] && [ "$COUNT" -lt 60 ]; do
    sleep 1
    COUNT=$((COUNT + 1))
done

if [ ! -d /sys/module/cfg80211 ]; then
    echo "ERROR: cfg80211 did not load"
    exit 1
fi

FW_PARAM=/sys/module/firmware_class/parameters/path
if [ -w "$FW_PARAM" ]; then
    echo "$MODDIR/firmware" > "$FW_PARAM"
    echo "firmware path set to $MODDIR/firmware"
else
    echo "WARNING: firmware_class.path is not writable"
fi

load_module() {
    NAME="$1"
    FILE="$2"

    if [ -d "/sys/module/$NAME" ]; then
        echo "SKIP: $NAME already loaded"
        return 0
    fi

    if [ ! -f "$FILE" ]; then
        echo "ERROR: missing $FILE"
        return 1
    fi

    echo "LOAD: $FILE"
    insmod "$FILE"
}

load_module mac80211 "$MODDIR/modules/mac80211.ko" || exit 1
load_module ath "$MODDIR/modules/ath.ko" || exit 1
load_module ath9k_hw "$MODDIR/modules/ath9k_hw.ko" || exit 1
load_module ath9k_common "$MODDIR/modules/ath9k_common.ko" || exit 1
load_module ath9k_htc "$MODDIR/modules/ath9k_htc.ko" || exit 1

echo "AR9271 module stack loaded"
