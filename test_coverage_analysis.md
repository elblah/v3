# Test Coverage Analysis for AI Coder

## Overall Coverage Summary
- **Total statements**: 4,499
- **Total covered**: 1,932 
- **Overall coverage**: 43%

## Well-Covered Modules (>80%)
- `stats.py`: 100%
- `datetime_utils.py`: 100%
- `path_utils.py`: 100%
- `token_estimator.py`: 98%
- `new_command.py`: 100%
- `retry_command.py`: 100%
- `config.py`: 81%
- `plugin_system.py`: 77%
- `diff_utils.py`: 77%

## Moderately Covered Modules (50-80%)
- `message_history.py`: 53%
- `tool_manager.py`: 82%
- `read_file.py`: 57%
- `write_file.py`: 68%
- `prompt_builder.py`: 73%

## Poorly Covered Modules (<50%)
- `streaming_client.py`: 16%
- `socket_server.py`: 15%
- `session_manager.py`: 20%
- `ai_processor.py`: 0%
- `compaction_service.py`: 20%
- `markdown_colorizer.py`: 60%
- `context_bar.py`: 22%
- `stream_processor.py`: 18%
- `tool_executor.py`: 53%
- `tool_formatter.py`: 40%
- `edit_file.py`: 36%
- `grep.py`: 16%
- `list_directory.py`: 12%
- `run_shell_command.py`: 21%
- `file_utils.py`: 44%
- `http_utils.py`: 15%
- `json_utils.py`: 28%
- `jsonl_utils.py`: 15%
- `log.py`: 80%
- `shell_utils.py`: 70%
- `stdin_utils.py`: 40%
- `stream_utils.py`: 0%
- `temp_file_utils.py`: 27%
- `commands/compact.py`: 13%
- `commands/debug.py`: 28%
- `commands/detail.py`: 27%
- `commands/edit.py`: 24%
- `commands/help.py`: 27%
- `commands/memory.py`: 25%
- `commands/sandbox.py`: 36%
- `commands/save.py`: 55%
- `commands/yolo.py`: 33%
- `prompt_history.py`: 45%
- `input_handler.py`: 61%
- `command_handler.py`: 93%

## Critical Missing Tests
The following modules need immediate attention due to very low coverage:

1. **Core functionality**:
   - `ai_processor.py` (0%) - Core AI processing logic
   - `streaming_client.py` (16%) - API communication
   - `socket_server.py` (15%) - Socket server functionality
   - `session_manager.py` (20%) - Session management
   - `compaction_service.py` (20%) - Memory compaction
   - `stream_processor.py` (18%) - Stream processing

2. **Internal tools**:
   - `edit_file.py` (36%) - Critical file editing functionality
   - `grep.py` (16%) - Text searching
   - `list_directory.py` (12%) - Directory listing
   - `run_shell_command.py` (21%) - Shell command execution

3. **Utility functions**:
   - `stream_utils.py` (0%) - Stream utilities
   - `http_utils.py` (15%) - HTTP utilities
   - `json_utils.py` (28%) - JSON utilities
   - `jsonl_utils.py` (15%) - JSONL utilities
   - `temp_file_utils.py` (27%) - Temporary file utilities

## Recommendations
1. Prioritize critical core modules with 0-20% coverage
2. Add integration tests for tool interactions
3. Create tests for error handling scenarios
4. Test edge cases and boundary conditions
5. Verify proper exception handling throughout the codebase