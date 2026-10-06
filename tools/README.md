# Pack dev tools

All tools run with the venv in `tools/.venv` from the repo root, for example
`tools/.venv/Scripts/python tools/smoke.py`. None of them are part of the pack (`/tools/` is in
`.packwizignore`). Generated state lives in `tools/.server` (headless test server) and `tools/.data`
(reports, recipe dumps); both are git-ignored. Recreate the venv with
`python -m venv tools/.venv` then `tools/.venv/Scripts/python -m pip install -r tools/requirements.txt`.

| Tool | What it does |
|---|---|
| `smoke.py` | Boots the pack on a headless NeoForge server with a fresh world, runs `/reload`, stops, and triages the logs. Exit code 1 on a crash, KubeJS error, or unknown error. |
| `logtriage.py` | Groups a log's warnings/errors, hides known-harmless ones (`known_issues.json`, each with a reason), and flags what's new since the last run. Default: the Prism client's `latest.log`; `--server` for the test server. |
| `pregen.py` | Pre-generates a fixed-seed area with Chunky (added to the test server for that run only) and reports chunks/second. `--place LAT,LON` centers it on a real-world spot in TFC: Real World. |
| `worldview/serve.py` | Browser viewer for a save: map (surface, height, TFC temperature/rainfall, lat/long grid), slices, Y distribution with host rock, chunk heatmaps. `--compare OTHER` adds a world B. |
| `recipes/dump.py` | Dumps every recipe, tag and block loot table from the pack via a dev-only KubeJS script on the test server, into `tools/.data/dumps/`; `index.json` also counts GregTech's ore veins (how many still generate). `--label NAME` to tag a before/after dump. |
| `recipes/serve.py` | Recipe explorer: how anything is made or used, first route from the world, why something is unreachable, duplicate materials, progression rules (`recipes/progression.json`), and dump comparison. `--world` picks the world used as the starting point. |
| `gt_update.py` | Reports newer GregTech nightlies (commits in between, dependency check against the pack); `--apply` swaps the pack's pinned build. |
| `mod_report.py` | Available updates with changelogs, client/server side audit against Modrinth, and license flags for redistribution. |

Typical loops:

- After any mod or script change: `smoke.py`, then `recipes/dump.py` and check the explorer's Progression page.
- Before and after a KubeJS integration script: `recipes/dump.py --label before`, change, `recipes/dump.py --label after`, then *Compare dumps*.
- World generation changes: `pregen.py --fresh --seed same-seed`, then `worldview/serve.py tools/.server/world-pregen --compare <older copy>`.
