# Step 0 Baseline: Pre-change Failures

Branch: `feature/step0-scaffold`, cut from `main` at `cd695f1`. Recorded 2026-10-10 on Windows 11, Python 3.13.7
(`backend/.venv`), Node via npm.

Commands:

```bash
# backend (from backend/)
PYTHONPATH=. .venv/Scripts/python -m pytest app/tests/ -q
# frontend (from Frontend/)
npm run build
npm run lint
```

## Failures found before any change

| # | Check | Failure | Cause | Resolution |
| --- | --- | --- | --- | --- |
| 1 | Backend tests | Whole suite errors at collection: `ImportError while loading conftest` → `ModuleNotFoundError: No module named 'psycopg'` (0 tests ran) | `app/core/database.py` builds the engine at import time. SQLAlchemy 2.1.3 is installed (`requirements.txt` allows `>=2.0.28,<3.0.0`), and 2.1 changed the default driver for a bare `postgresql://` URL from psycopg2 to psycopg v3. Only `psycopg2-binary` is installed. | **Fixed.** `Settings.DATABASE_URL` validator rewrites `postgresql://` / `postgres://` to `postgresql+psycopg2://` (covers the app engine and `alembic/env.py`). Test added: `app/tests/test_settings.py`. |
| 2 | Frontend lint | `oxlint : The term 'oxlint' is not recognized` | `package.json` runs `oxlint` and `.oxlintrc.json` is committed, but `oxlint` was never a dependency. | **Fixed.** Added `oxlint` to `devDependencies`. |
| 3 | Frontend build | `The token '&&' is not a valid statement separator in this version.` | Machine-local: the user-level `~/.npmrc` sets `script-shell=powershell.exe`, and Windows PowerShell 5.1 has no `&&`. The script `tsc -b && vite build` is fine under npm's default shell (`cmd.exe` on Windows, `sh` elsewhere). | **Not a repo defect; no repo change.** `npm run build --script-shell=cmd.exe` builds cleanly. Remove the `script-shell` line from `~/.npmrc` (or switch to PowerShell 7) to fix locally. |

## Results after fixes

- Backend: **221 passed**, 0 failed, 0 xfail (217 existing + 4 new).
- Frontend build: passes (`tsc -b` clean, `vite build` OK).
- Frontend lint: **0 errors**, exit 0. 18 warnings remain (not failures, left for later work):
  - `no-unused-vars` on unused catch params: `api/client.ts`, `store/useAuthStore.ts`, `store/useWorldStore.ts`, `pages/SignIn.tsx`, `pages/WritingRoom.tsx`
  - `react(set-state-in-effect)`: `pages/Manuscripts.tsx` (x2), `pages/Worlds.tsx`, `pages/WritingRoom.tsx`
  - `react-hooks(exhaustive-deps)`: `pages/Manuscripts.tsx`, `pages/Worlds.tsx`, `pages/WritingRoom.tsx`
  - `no-useless-escape`: `pages/WritingRoom.tsx:229`

## Known noise (not failures)

- Backend emits ~1,770 `DeprecationWarning`s, mostly `datetime.utcnow()` in models, `core/security.py`,
  `workers/tasks/*`, and `tests/test_phase1_ordering.py`. This conflicts with `.ai/RULES.md` Rule 6.2 and is worth
  its own change.
