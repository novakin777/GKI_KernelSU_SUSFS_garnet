#!/system/bin/sh

MODDIR=${0%/*}
LOG="$MODDIR/ath9k_htc.log"

exec >>"$LOG" 2>&1

echo
echo "===== garnet AR9271 autoload gate: $(date) ====="

if [ ! -f "$MODDIR/enable-autoload" ]; then
    echo "SAFE MODE: autoload is disabled"
    echo "Test manually first: su -c sh $MODDIR/load.sh"
    exit 0
fi

echo "Autoload enabled"
exec "$MODDIR/load.sh"
