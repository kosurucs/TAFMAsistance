---
description: "Sync .github/instructions/ and copilot-instructions.md after code changes. Run this after completing any significant code change to keep agent instructions accurate."
---

Synchronise the `.github/instructions/` files and `copilot-instructions.md` to reflect recent code changes.

## Steps

### 1. Identify Changed Areas

List the files that were recently changed. If not provided, check git status:
```bash
cd c:\Source\TAFMAsistance\TAFMAsistance && git diff --name-only HEAD~1
```

Or review the changes described by the user.

### 2. Map to Instruction Files

For each changed file, identify which instruction file owns it:

| Changed Area | Instruction File |
|-------------|-----------------|
| `trading_bot/**/*.py` | `python-backend.instructions.md` |
| `trading_bot/src/utils/risk_manager.py` | `trading-domain.instructions.md` |
| `trading_bot/src/utils/technical_analysis.py` | `trading-domain.instructions.md` |
| `trading_bot/src/utils/scenario_engine.py` | `trading-domain.instructions.md` |
| `trading_bot/src/utils/rr_calculator.py` | `trading-domain.instructions.md` |
| `trading_bot/src/api/**` | `python-backend.instructions.md` |
| `trading_bot/scripts/*.sql` | `database.instructions.md` |
| `trading_ui/src/**` | `react-ui.instructions.md` |
| `llm_training/**` | `llm-training.instructions.md` |
| New top-level files, architecture change | `copilot-instructions.md` |

### 3. Delegate to Doc-Sync Agent

For each identified instruction file, invoke the `doc-sync` subagent with:
- The list of changed source files
- The specific instruction file to update

The `doc-sync` agent will read both the changed code and the instruction file, then update only what is stale.

### 4. Update Key Files Table

If any new key files were created (new utility, new router, new tool), add them to the Key Files table in `.github/copilot-instructions.md`.

### 5. Report

After all syncs complete, present a summary:
```
Updated:
- trading-domain.instructions.md: Added Williams %R to indicator table
- python-backend.instructions.md: Updated router registration pattern

No changes needed:
- react-ui.instructions.md: No UI files changed
- database.instructions.md: No schema changes
```
