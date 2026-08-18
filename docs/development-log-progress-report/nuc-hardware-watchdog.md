# The hardware watchdog, and the deny-list that hid it

Machine-local config on the NUC, recorded here because it is invisible from the
repo and took three reboots to get right.

## What it is for

The NUC froze solid on 8 August and stayed frozen for nine days
([post-mortem](../postmortems/2026-08-08-nuc-freeze.md)). Nothing in userspace
can catch that: the thing that would report the freeze is the thing that died.
The Intel TCO chip can, because it lives outside the CPU's control. systemd
pets `/dev/watchdog` every few seconds, and if that stops for 30 seconds the
chip power-cycles the box.

## What went wrong twice

The obvious ways to load a module at boot both **failed silently**:

```
/etc/modules-load.d/itco-watchdog.conf     -> did nothing, reported success
/etc/initramfs-tools/modules               -> did nothing, reported success
```

Two reboots came up with no `/dev/watchdog` at all while every config file
looked correct. The reason:

```
/lib/modprobe.d/blacklist_linux_7.0.0-29-generic.conf:26: blacklist iTCO_wdt
Module 'iTCO_wdt' is deny-listed (by kmod)
```

The kernel package deny-lists it. A `blacklist` line stops a module being
pulled in *automatically* — by alias, by udev, by `modules-load.d`, by the
initramfs — and `systemd-modules-load` reports success when it skips one. So
the log said everything worked, and nothing had.

An **explicit** `modprobe iTCO_wdt` is still honoured. That is the whole fix.

## What is installed

`/etc/systemd/system/itco-watchdog.service` — a oneshot before `sysinit.target`
that runs exactly that explicit modprobe. Enabled.

`/etc/systemd/system.conf.d/watchdog.conf`:

```
RuntimeWatchdogSec=30s
RebootWatchdogSec=5min
```

## Verified

Third reboot, nothing done by hand:

```
iTCO_wdt               16384  2
identity  iTCO_wdt
state     active
timeout   30
timeleft  30
systemd: 30s
```

## Worth knowing

The distro deny-lists this module deliberately — on some hardware `iTCO_wdt`
causes spurious reboots. On this NUC10i7FNH it initialises cleanly and reports
a real TCO device. We are overriding a vendor default on purpose, and the
trade is deliberate: a spurious reboot costs a minute, and the failure it
guards against cost nine days.

If this box ever starts rebooting for no reason, look here first.
