#!/usr/bin/env python3
# V3: enable the monitor netdev TX queue after the monitor vdev is ready.
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("kernel/sm7435-modules")
HDD = ROOT / "qcom/opensource/wlan/qcacld-3.0/core/hdd"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1))
    print(f"patched {path}")


header = HDD / "inc/wlan_hdd_tx_rx.h"
replace_once(
    header,
    "netdev_tx_t hdd_hard_start_xmit(struct sk_buff *skb, struct net_device *dev);\n",
    "netdev_tx_t hdd_hard_start_xmit(struct sk_buff *skb, struct net_device *dev);\n"
    "\n"
    "#ifdef FEATURE_MONITOR_MODE_SUPPORT\n"
    "netdev_tx_t hdd_mon_hard_start_xmit(struct sk_buff *skb,\n"
    "                                    struct net_device *dev);\n"
    "#endif\n",
)

main = HDD / "src/wlan_hdd_main.c"
replace_once(
    main,
    "/* Monitor mode net_device_ops, doesnot Tx and most of operations. */\n"
    "static const struct net_device_ops wlan_mon_drv_ops = {\n"
    "\t.ndo_open = hdd_mon_open,\n"
    "\t.ndo_stop = hdd_stop,\n"
    "\t.ndo_get_stats = hdd_get_stats,\n"
    "};",
    "/* Monitor mode net_device_ops with raw 802.11 TX support. */\n"
    "static const struct net_device_ops wlan_mon_drv_ops = {\n"
    "\t.ndo_open = hdd_mon_open,\n"
    "\t.ndo_stop = hdd_stop,\n"
    "\t.ndo_start_xmit = hdd_mon_hard_start_xmit,\n"
    "\t.ndo_get_stats = hdd_get_stats,\n"
    "};",
)

replace_once(
    main,
    "\tif (!ret) {\n"
    "\t\tparam.policy = BBM_DRIVER_MODE_POLICY;\n",
    "\tif (!ret) {\n"
    "\t\t/* The stock monitor netdev is RX-only and remains stopped. */\n"
    "\t\thdd_debug(\"Enabling monitor Tx queues without carrier\");\n"
    "\t\twlan_hdd_netif_queue_control(\n"
    "\t\t\tadapter, WLAN_START_ALL_NETIF_QUEUE,\n"
    "\t\t\tWLAN_CONTROL_PATH);\n"
    "\n"
    "\t\tparam.policy = BBM_DRIVER_MODE_POLICY;\n",
)

txrx = HDD / "src/wlan_hdd_tx_rx.c"
replace_once(
    txrx,
    "#include \"dp_txrx.h\"\n"
    "#if defined(WLAN_SUPPORT_RX_FISA)\n"
    "#include \"dp_fisa_rx.h\"\n"
    "#else\n"
    "#include <net/ieee80211_radiotap.h>\n"
    "#endif\n"
    "#include <ol_defines.h>",
    "#include \"dp_txrx.h\"\n"
    "#include <net/ieee80211_radiotap.h>\n"
    "#include \"ol_txrx.h\"\n"
    "#if defined(WLAN_SUPPORT_RX_FISA)\n"
    "#include \"dp_fisa_rx.h\"\n"
    "#endif\n"
    "#include <ol_defines.h>",
)

marker = "\n#ifdef TX_MULTIQ_PER_AC\n"
function = r'''

#ifdef FEATURE_MONITOR_MODE_SUPPORT
/**
 * hdd_mon_hard_start_xmit() - transmit raw 802.11 from monitor mode
 * @skb: radiotap + IEEE 802.11 frame supplied by userspace
 * @dev: monitor net_device
 *
 * This implementation consumes only the radiotap length. Rate/channel and other TX
 * controls remain governed by the existing monitor configuration. The raw
 * IEEE 802.11 frame is submitted to the existing qcacld non-standard TX path
 * on the monitor vdev.
 *
 * Return: NETDEV_TX_OK. The skb is consumed on every path.
 */
netdev_tx_t hdd_mon_hard_start_xmit(struct sk_buff *skb,
                                    struct net_device *dev)
{
    struct hdd_adapter *adapter = WLAN_HDD_GET_PRIV_PTR(dev);
    struct ieee80211_radiotap_header *rtap;
    ol_txrx_soc_handle soc;
    qdf_nbuf_t rejected;
    uint16_t rt_len;
    uint8_t vdev_id;
    enum ol_tx_spec tx_spec;

    if (unlikely(!skb || !adapter))
        goto drop;

    if (unlikely(skb->len < sizeof(*rtap)))
        goto drop;

    rtap = (struct ieee80211_radiotap_header *)skb->data;
    if (unlikely(rtap->it_version != 0))
        goto drop;

    rt_len = ieee80211_get_radiotap_len(skb->data);
    if (unlikely(rt_len < sizeof(*rtap) || skb->len <= rt_len))
        goto drop;

    skb_pull(skb, rt_len);
    skb_reset_mac_header(skb);
    skb->next = NULL;

    soc = cds_get_context(QDF_MODULE_ID_SOC);
    if (unlikely(!soc))
        goto drop;

    /* hdd_enable_monitor_mode() uses pdev id 0 on this Adrastea target. */
    vdev_id = ol_txrx_get_mon_vdev_from_pdev(soc, 0);
    if (unlikely(vdev_id == 0xea))
        goto drop;

    tx_spec = OL_TX_SPEC_RAW | OL_TX_SPEC_NO_AGGR | OL_TX_SPEC_NO_ENCRYPT;
    rejected = cdp_tx_non_std(soc, vdev_id, tx_spec, skb);

    while (rejected) {
        struct sk_buff *next = rejected->next;

        rejected->next = NULL;
        dev_kfree_skb_any(rejected);
        rejected = next;
    }

    return NETDEV_TX_OK;

drop:
    if (skb)
        dev_kfree_skb_any(skb);

    return NETDEV_TX_OK;
}
#endif /* FEATURE_MONITOR_MODE_SUPPORT */
'''
replace_once(txrx, marker, function + marker)

print("qcacld monitor raw-injection V3 patch applied successfully")
