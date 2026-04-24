# BANE-NLP Codebase Restructuring Plan

The root directory of `d:\Bane_NLP` is currently cluttered with many Python scripts that should be modularized into proper packages. This plan outlines how we will move these files into designated folders and systematically update all `import` statements to prevent the application from breaking.

## User Review Required

Please review the proposed folder structure below. This is a **major structural change**. If any scripts are missing or if you prefer different folder names (e.g., `interfaces` instead of `channels`), let me know before I execute.

> [!WARNING]
> Moving files requires updating `import` statements across the entire codebase. While I will carefully update these, there is always a slight risk of a temporary runtime error if a dynamic import is missed. We will need to thoroughly test `run.py` after the restructuring.

## Proposed Changes

We will create the following new directories (packages) and move the corresponding files into them. `__init__.py` files will be created to make them proper Python packages.

### 1. `core/` (Core System & Utilities)
*Houses the fundamental backend systems, configuration, and security.*
- `bane_core.py` -> `core/bane_core.py`
- `browser_bridge.py` -> `core/browser_bridge.py`
- `command_router.py` -> `core/command_router.py`
- `config.py` -> `core/config.py`
- `database.py` -> `core/database.py`
- `logger.py` -> `core/logger.py`
- `security.py` -> `core/security.py`
- `system_stats.py` -> `core/system_stats.py`

### 2. `channels/` (Platform Integrations)
*Houses the external messaging bots and formatting tools.*
- `telegram_bot.py` -> `channels/telegram_bot.py`
- `messenger_bot.py` -> `channels/messenger_bot.py`
- `channel_adapter.py` -> `channels/channel_adapter.py`
- `telegram_formatter.py` -> `channels/telegram_formatter.py`

### 3. `services/` (Standalone Handlers)
*Houses specific multimedia or external services.*
- `email_handler.py` -> `services/email_handler.py`
- `voice_engine.py` -> `services/voice_engine.py`

### 4. `pipeline/` (Existing folder, adding missed files)
*Moving pipeline-related builders that were left in the root.*
- `context_builder.py` -> `pipeline/context_builder.py`
- `payload_builder.py` -> `pipeline/payload_builder.py`
- `response_handler.py` -> `pipeline/response_handler.py`

### Files Staying in Root:
- `run.py` (Main execution entry point)
- `.bat` files (`START_BANE.bat`, `STOP_BANE.bat`)
- Database (`bane_data.db`)
- `.yml`, `.csv`, `.txt` config files

## Open Questions
- Do you agree with moving `config.py` into the `core/` folder, or would you prefer it stays in the root directory for easier access when you want to change settings?
- Are you currently running BANE-NLP? If yes, the `START_BANE.bat` background process must be stopped before we can safely move these files and rewrite the imports.

## Verification Plan
1. Stop the BANE process if running.
2. Create directories and `__init__.py` files.
3. Move files using terminal commands.
4. Use `grep_search` to find all broken import references (e.g., `from browser_bridge`, `import telegram_bot`, `from config`).
5. Use `replace_file_content` to rewrite imports to use the new package namespaces (e.g., `from core.browser_bridge`, `from channels.telegram_bot`, `from core.config`).
6. Run a dry run of `python run.py` to catch any `ModuleNotFoundError`s before restarting the daemon.
