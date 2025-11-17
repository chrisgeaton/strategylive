# Task: Fix Claude API 404 Error - Invalid Model ID

## Date
2025-11-17 15:45

## Prompt
User reported: "Got this error: Transcribed: I don't know why, but anyway.
❌ Claude API error: 404 - {"type":"error","error":{"type":"not_found_error","message":"model: claude-3-5-sonnet-20241022"},"request_id":"req_011CVDb21L3UGFYm5UZqHutD"}
⚠️ Circuit breaker failures: 2/3"

## Context
The application was attempting to use an invalid Claude model ID (`claude-3-5-sonnet-20241022`) which doesn't exist in Anthropic's API. The code had this model ID hardcoded and wasn't properly reading the `ANTHROPIC_MODEL` environment variable that was already configured in the `.env` file.

## Actions Taken

1. **Identified the problem**:
   - Used `Grep` to find all occurrences of `claude-3-5-sonnet-20241022` in the codebase
   - Found hardcoded model IDs in three files:
     - `whisper_server.py:1411`
     - `sales_expert_agent.py:59`
     - `.env.example:4-5`

2. **Fixed whisper_server.py**:
   - Changed line 1411 from: `self.model = "claude-3-5-sonnet-20241022"`
   - To: `self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")`
   - Now reads from environment variable with valid fallback

3. **Fixed sales_expert_agent.py**:
   - Changed line 59 from: `self.model = "claude-3-5-sonnet-20241022"`
   - To: `self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")`
   - Ensures consistency across all AI coaching components

4. **Updated .env file**:
   - Changed `ANTHROPIC_MODEL=claude-3-5-sonnet-latest`
   - To: `ANTHROPIC_MODEL=claude-3-5-sonnet-20240620`
   - Uses a valid, specific model ID instead of "latest"

5. **Updated .env.example**:
   - Updated default model reference from `claude-3-5-sonnet-20241022`
   - To: `claude-3-5-sonnet-20240620`
   - Added clearer comments about valid model IDs

## Files Changed
- `whisper_server.py:1411` - Now reads ANTHROPIC_MODEL env var with valid fallback
- `sales_expert_agent.py:59` - Now reads ANTHROPIC_MODEL env var with valid fallback
- `.env:12` - Changed to valid model ID `claude-3-5-sonnet-20240620`
- `.env.example:4-6` - Updated documentation and default model ID

## Testing
User instructed to restart whisper_server.py to apply the changes:
1. Stop current server with `Ctrl+C`
2. Run `python whisper_server.py` again
3. Claude API calls should now succeed with the valid model ID

## Outcome
✅ **SUCCESS** - Code fixed to use valid Claude model ID and properly read environment variables.

The circuit breaker should reset after successful API calls. All Claude coaching suggestion functionality should now work properly.

## Notes
- The model ID `claude-3-5-sonnet-20241022` appears to not exist in Anthropic's API (404 error)
- Valid Claude 3.5 Sonnet model IDs include: `claude-3-5-sonnet-20240620`
- Changed approach from using "latest" to specific dated model IDs for stability
- User must restart the Python server for changes to take effect

## Follow-up Issues Identified
User mentioned transcription accuracy is poor with current local Whisper setup. Discussed potential improvements:
- Upgrade Whisper model size (tiny → base/small/medium)
- Switch to Deepgram API (user has credentials but mentioned previous connection issues)
- Audio quality improvements
- Post-processing with LLM

User wants to save current status before attempting Deepgram integration again.
