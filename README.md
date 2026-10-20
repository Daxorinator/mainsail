# Mainsail + speed limit display (fork)

This is a fork of [Mainsail](https://github.com/mainsail-crew/mainsail) that
adds one row under the ETA on the print status panel showing **what is
currently limiting the print speed**: max volumetric flow, max velocity,
acceleration, cornering, speed override, minimum layer time, Z/extruder caps
and so on. It is designed for a **Creality K1** running the Guilouz Creality
Helper Script, and needs the Klipper extra in
[`klipper-speed-limiter/`](klipper-speed-limiter/).

| Part | Where | What it does |
| --- | --- | --- |
| Klipper extra | `klipper-speed-limiter/` | Works out the speed limit and publishes it as the `speed_limiter` Klipper object |
| Mainsail patch | `patches/speed-limit-display.patch` | Adds the row to `PrintstatusPrinting.vue` (hidden if `speed_limiter` is absent) and a locale string |
| Release workflow | `.github/workflows/release-patched.yml` | Builds and publishes patched Mainsail releases automatically |

## How upstream releases are pulled in, patched and re-released
The default branch of this fork is `speed-limiter`. It holds only the patch,
the workflow and the Klipper extra. `develop` and the other upstream branches
are untouched, and upstream's own workflows are removed from this branch so
none of them run here. The release workflow runs every 6 hours, and on demand
from the Actions tab:

1. Ask GitHub for the latest release of `mainsail-crew/mainsail`.
2. If this fork already has a release with the same tag, stop.
3. Otherwise check out that exact upstream tag (not a merge of branches),
   apply every file in `patches/`, run `npm ci && npm run build` on Node 22,
   and check the build contains the new UI.
4. Publish a release in this fork with the **same tag** as upstream (for
   example `v2.19.0`) and `mainsail.zip` attached. Using the same tag keeps
   Moonraker's version comparison working.

Notes:
- If the patch no longer applies after an upstream change, the run fails and
  GitHub notifies you. Update `patches/speed-limit-display.patch`, then run the
  workflow again with *force* to replace the release.
- Pre-releases are ignored. Only upstream's "latest" release is built.
- GitHub disables scheduled workflows in repositories with no activity for 60
  days. Re-enable it from the Actions tab if that happens.
- To run it by hand: Actions, *Release patched Mainsail*, *Run workflow*. You
  can give a tag to build, and tick *force* to rebuild an existing one.

## Using it on the K1
1. **One-time install.** Moonraker thinks an already-installed `v2.19.0` is
   current, so deploy the first patched build by hand. Download `mainsail.zip`
   from the [latest release](../../releases/latest), copy it to the K1, and run
   `sh install-k1.sh mainsail mainsail.zip` from `klipper-speed-limiter/`.
2. **Klipper side.** Follow `klipper-speed-limiter/README.md`.
3. **Future updates.** In `moonraker.conf`, replace the helper script's
   `[update_manager mainsail]` block with the one in
   `klipper-speed-limiter/moonraker.conf.example`, which points at this fork.
   Mainsail's update button then installs patched releases as they appear.
   Reinstalling Mainsail with the Guilouz helper script installs upstream's
   unpatched build, so redeploy the zip afterwards.

---

<p align="center">
  <a>
    <img src="https://raw.githubusercontent.com/mainsail-crew/docs/master/assets/img/logo.png" alt='Mainsail logo' height="152">
    <h1 align="center">Mainsail</h1>
  </a>
</p>
<p align="center">
  Makes Klipper more accessible by adding a lightweight, responsive web user interface, centred around an intuitive and consistent design philosophy.
</p>
<p align="center">
  <a aria-label="Downloads" href="https://github.com/mainsail-crew/mainsail/releases">
    <img src="https://img.shields.io/github/downloads/mainsail-crew/mainsail/total?style=flat-square">
  </a>
  <a aria-label="Stars" href="https://github.com/mainsail-crew/mainsail/stargazers">
    <img src="https://img.shields.io/github/stars/mainsail-crew/mainsail?style=flat-square">
  </a>
  <a aria-label="Forks" href="https://github.com/mainsail-crew/mainsail/network/members">
    <img src="https://img.shields.io/github/forks/mainsail-crew/mainsail?style=flat-square">
  </a>
  <a href="https://hosted.weblate.org/engage/mainsail/">
    <img src="https://hosted.weblate.org/widget/mainsail/mainsail/svg-badge.svg" alt="Übersetzungsstatus" />
  </a>
  <a aria-label="License" href="https://github.com/mainsail-crew/mainsail/blob/develop/LICENSE">
    <img src="https://img.shields.io/github/license/mainsail-crew/mainsail?style=flat-square">
  </a>
  <a aria-label="Last commit" href="https://github.com/mainsail-crew/mainsail/commits/">
    <img src="https://img.shields.io/github/last-commit/meteyou/mainsail?style=flat-square">
  </a>
  <br />
  <a aria-label="Size" href="https://github.com/mainsail-crew/mainsail/">
    <img src="https://img.shields.io/github/repo-size/meteyou/mainsail?style=flat-square">
  </a>
  <a aria-label="Discord" href="https://discord.gg/skWTwTD">
    <img src="https://img.shields.io/discord/758059413700345988?color=%235865F2&label=discord&logo=discord&logoColor=white&style=flat-square">
  </a>
  <a aria-label="Patreon" href="https://www.patreon.com/meteyou">
    <img src="https://img.shields.io/endpoint.svg?url=https%3A%2F%2Fshieldsio-patreon.vercel.app%2Fapi%3Fusername%3Dmeteyou%26type%3Dpatrons&style=flat-square">
  </a>
</p>

## Getting Started

Visit [docs.mainsail.xyz/setup](https://docs.mainsail.xyz/setup) to get started with Mainsail.

Mainsail is also available in remote mode on [http://my.mainsail.xyz](http://my.mainsail.xyz). Find
out [more](https://docs.mainsail.xyz/setup#mymainsailxyz).

## Documentation

Visit [docs.mainsail.xyz](https://docs.mainsail.xyz) to view the full documentation.  
You can find the latest release notes [here](https://github.com/mainsail-crew/mainsail/releases).

## Screenshots

![screenshot-dashboard](https://raw.githubusercontent.com/mainsail-crew/docs/master/assets/img/screenshot.png)
![Features](https://raw.githubusercontent.com/mainsail-crew/docs/master/assets/img/features.png)

## Features

- **Responsive Web Interface:** _Optimized for desktops, tablets and mobile devices_
- **Printer Farm:** _Supports multiple 3D printers_
- **[Localization](https://docs.mainsail.xyz/features/localization):** _Choose between 12 different languages_
- **File Manager:** _Delete, rename and upload your G-Code and config files_
- **File Editor:** _Edit G-Code, config, and markdown files with syntax highlighting in your browser_
- **[Print History](https://docs.mainsail.xyz/features/history):** _See your previous prints and their status_
- **[Statistics](https://docs.mainsail.xyz/features/history):** _View how much time your printer has been in use and the number of jobs that have succeeded or failed_
- **Job Queue:** _Queue multiple jobs and add them directly from your slicer_
- **[Temperature Presets](https://docs.mainsail.xyz/features/presets):** _Manage different temperature presets for easy preheating_
- **[Bed Mesh Visualisation](https://docs.mainsail.xyz/features/bedmesh):** _View your bed using a 3D mesh graph_
- **G-Code Viewer:** _View a 3D render of your print and follow the progress_
- **Multi-Webcam Support:** _View your print from different angles with multiple webcams_
- **Timelapse Integration:** _Automatically record a timelapse of your print using [moonraker-timelapse](https://github.com/mainsail-crew/moonraker-timelapse)_
- **Power Control:** _Control power devices such as relays, TP-Link and Tasmota devices, and more_
- **Powerful Macro-Management:** _Manage your macros on a micro level_
- **[Configurable Dashboard](https://docs.mainsail.xyz/features/dashboard-organisation):** _Create your own personal dashboard_
- **[Theming Support](https://docs.mainsail.xyz/features/theming):** _Customizable user interface including logos, backgrounds, and custom CSS_
- **[Additional Sensors](https://docs.mainsail.xyz/quicktips/additional-sensors):** _Add extra sensors to the temperature graph_
- **Exclude Objects:** _Exclude parts of your print <sup>(not officially supported by Klipper yet)</sup>_

## Help and Support

Do you need help or just want to talk? Join our active community on [Discord](https://discord.gg/skWTwTD)!

Did you find a bug or did you thought of a feature?
Please create an [Issue](https://github.com/mainsail-crew/mainsail/issues) in GitHub and let us know.

## Official Sponsors

<p align='center'>
    <img src="https://raw.githubusercontent.com/mainsail-crew/docs/master/assets/img/logo-bigtreetech.png" alt='Mainsail logo' width="150">
</p>

**BIGTREETECH** is the official mainboard partner of Mainsail. BIGTREETECH is committed to developing innovative and competitive products to better serve the 3D printing community.

## Support Mainsail

Mainsail is primarily developed and maintained by meteyou. To keep the project going he invests his free time, almost
every day. To motivate him (☕🍺😜) there are several ways to support him:

[![patreon](https://img.shields.io/badge/patreon-participate-yellow.svg?style=flat-square)](https://www.patreon.com/meteyou)
[![kofi](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=flat-square)](https://ko-fi.com/mainsail)

## Contributing

Contributions to Mainsail are always welcome!

- 📥 Pull requests and 🌟 Stars are always welcome.
- Read our [contributing guidelines](CONTRIBUTING.md) to get started,
  or find us on [Discord](https://discord.gg/mainsail), we will take the time to guide you.

Looking for a first issue to tackle?

- We tag issues with [![Good First Issue](https://img.shields.io/github/issues/mainsail-crew/mainsail/good%20first%20issue.svg)](https://github.com/mainsail-crew/mainsail/issues?q=is%3Aopen+is%3Aissue+label%3A%22good+first+issue%22) when we think they are well suited for people who are new to the codebase or OSS in general.
- [Talk to us](https://discord.gg/mainsail), we'll find something that suits your skills and learning interest.

## Credit, sources and inspiration

- [Kevin O'Connor](https://github.com/KevinOConnor) for the awesome 3D printer firmware [Klipper](https://github.com/KevinOConnor/klipper)
- [Eric Callahan (arksine)](https://github.com/Arksine) for [Moonraker (Klipper API)](https://github.com/Arksine/moonraker). Without Moonraker, Mainsail would not be possible.
- [lixxbox](https://github.com/lixxbox) for the Mainsail logo & Docs
- [Vue.js](https://vuejs.org/): The Progressive JavaScript Framework
- [Vuetify](https://vuetifyjs.com/): Material Design Component Framework for Vue.js

Massive thanks to the whole [Voron Design](http://vorondesign.com/) community. Without them such a project would not be
possible.

[Full Credits & License information](https://docs.mainsail.xyz/credits)
