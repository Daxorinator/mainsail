# Speed-limiter fork of Mainsail

Default branch `speed-limiter` only holds `patches/` and the release workflow;
the `develop`/`main` branches are untouched upstream. A scheduled workflow
builds each new upstream release with the patches applied and publishes
`mainsail.zip` as a release here. Point Moonraker at it:

    [update_manager mainsail]
    type: web
    channel: stable
    repo: Daxorinator/mainsail
    path: /usr/data/mainsail

Requires the `speed_limiter` Klipper extra from klipper-print-limiter-plugin.
If the patch stops applying after an upstream change, the workflow fails and
`patches/speed-limit-display.patch` needs refreshing.
