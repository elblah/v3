<system-reminder>
ECONOMY MODE ACTIVATED:

**OBJECTIVE:** Minimize tool calls and API requests. Every tool invocation has a cost - batch aggressively.

**MODE:** Economy Active - Persistent until cancelled

**CRITICAL RULES:**

1. **BULK READING:**
   - Read files in ONE call with large `limit` (e.g., 300-500 lines) instead of multiple small reads
   - Default 150 lines is acceptable for small files, but use larger limits for substantial files
   - NEVER read a file multiple times to "see more" - read it all at once
   - Use grep with higher `max_results` and `context` to get comprehensive results in one call

2. **PARALLEL TOOL CALLS:**
   - When you need to read multiple files, invoke ALL read_file calls in a SINGLE function_calls block
   - When you need to search and read, do ALL searches and reads in parallel
   - NEVER serialize operations that can run in parallel

3. **BATCH EDITS:**
   - Plan ALL edits before making any changes
   - If a file needs multiple edits, use edit_file with `old_string`/`new_string` for each
   - For substantial rewrites, use a single write_file instead of many edit_file calls

4. **THINK BEFORE ACTING:**
   - Plan the entire operation before starting
   - Identify all files you'll need to read - read them ALL at once
   - Identify all searches needed - run them ALL at once
   - Then make ALL edits in the minimum number of operations

5. **AVOID REDUNDANCY:**
   - Don't re-read files you've already read in this session
   - Don't search for something you already found
   - Don't list directories you've already explored

**ANTI-PATTERN (WRONG):**
```
read_file(path="file1.py")        # Call 1
read_file(path="file2.py")        # Call 2  
read_file(path="file1.py", offset=150)  # Call 3 - redundancy!
```

**CORRECT PATTERN:**
```
read_file(path="file1.py", limit=500)  # All in one call
read_file(path="file2.py", limit=500)  # Parallel with other reads
```

**MEASUREMENT:** Success = fewer tool roundtrips, not fewer operations completed.
</system-reminder>
