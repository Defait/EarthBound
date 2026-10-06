# Pack dev tools

All tools run with the venv in `tools/.venv` from the repo root, for example
`tools/.venv/Scripts/python tools/smoke.py`. None of them are part of the pack (`/tools/` is in
`.packwizignore`). Generated state lives in `tools/.server` (headless test server) and `tools/.data`
(reports, recipe dumps); both are git-ignored. Recreate the venv with
`python -m venv tools/.venv` then `tools/.venv/Scripts/python -m pip install -r tools/requirements.txt`.

| Tool | What it does |
|---|---|
| `smoke.py` | Boots the pack on a headless NeoForge server with a fresh world, runs `/reload`, stops, and triages the logs. Also runs `smoke_checks.js` on the server (e.g. that GregTech's recipe-viewer mixins apply to the pinned JEI). Exit code 1 on a crash, KubeJS error, or unknown error. |
| `startat_test.py` | Checks the `/startat` command on a fresh headless world: the start-point finder for a few real places, then the command itself as a non-op fake player (open water, first use, second use, bad input). Exit code 1 on any failure. |
| `logtriage.py` | Groups a log's warnings/errors, hides known-harmless ones (`known_issues.json`, each with a reason), and flags what's new since the last run. Default: the Prism client's `latest.log`; `--server` for the test server. |
| `pregen.py` | Pre-generates a fixed-seed area with Chunky (added to the test server for that run only) and reports chunks/second. `--place LAT,LON` centers it on a real-world spot in TFC: Real World. |
| `worldview/serve.py` | Browser viewer for a save: map (surface, height, TFC temperature/rainfall, lat/long grid), slices, Y distribution with host rock, chunk heatmaps. `--compare OTHER` adds a world B. |
| `recipes/dump.py` | Dumps every recipe, tag and block loot table from the pack via a dev-only KubeJS script on the test server, into `tools/.data/dumps/`; `index.json` also counts GregTech's ore veins (how many still generate). `--label NAME` to tag a before/after dump. |
| `recipes/serve.py` | Recipe explorer: how anything is made or used, first route from the world, why something is unreachable, duplicate materials, progression rules (`recipes/progression.json`), and dump comparison. `--world` picks the world used as the starting point. |
| `quests/build.py` | Builds the FTB Quests book (`config/ftbquests/quests/`) from `quests/route.json`, then checks the route against the progression checker: every quest item exists and is reachable, and no quest comes before its prerequisites. Edit `route.json`, not the generated files. |
| `gt_update.py` | Reports newer GregTech nightlies (commits in between, dependency check against the pack); `--apply` swaps the pack's pinned build. |
| `mod_report.py` | Available updates with changelogs, client/server side audit against Modrinth, and license flags for redistribution. |

Typical loops:

- After any mod or script change: `smoke.py`, then `recipes/dump.py` and check the explorer's Progression page, then `quests/build.py` (the route check uses the new dump).
- Before and after a KubeJS integration script: `recipes/dump.py --label before`, change, `recipes/dump.py --label after`, then *Compare dumps*.
- After a KubeJS, TFC: Real World or NeoForge update: `startat_test.py` too (the command leans on their internals).
- World generation changes: `pregen.py --fresh --seed same-seed`, then `worldview/serve.py tools/.server/world-pregen --compare <older copy>`.
