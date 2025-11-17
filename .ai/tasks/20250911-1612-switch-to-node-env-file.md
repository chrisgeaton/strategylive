# Task: Switch server to Node --env-file and remove dotenv dependency

## Date
2025-09-11 16:12

## Prompt
can you do this for me?

## Context
The server failed with `ERR_MODULE_NOT_FOUND: dotenv` because dependencies were not installed yet. To reduce moving parts and leverage Node v22 features, load environment variables via Node’s built-in `--env-file` flag and drop the code-level `dotenv` import.

## Actions Taken
1. Removed `import 'dotenv/config'` from `server/index.js`.
2. Updated `package.json` scripts to use `node --env-file=.env` for `start` and `dev:server`.
3. Removed `dotenv` from dependencies.

## Files Changed
- `server/index.js` — removed dotenv import.
- `package.json` — scripts updated; removed dotenv dependency.

## Testing
- Run `npm run dev:server` with a valid `.env` present; server starts and reads env without dotenv.

## Outcome
Server now loads env vars via Node’s `--env-file` and no longer requires `dotenv`.

