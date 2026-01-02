# Subagents Skill References

This directory contains detailed reference materials for the subagents parallel execution system.

## 📚 Reference Documents

### [SUBAGENT_GUIDELINES.md](./SUBAGENT_GUIDELINES.md)
Essential guidelines for safe subagent execution. **CRITICAL READING** before implementing or using subagents. Covers:
- Safe temporary directory usage (NEVER use project root)
- File safety and cleanup strategies  
- Error handling and partial failure recovery
- Memory management and performance optimization

### [TIMEOUT_GUIDELINES.md](./TIMEOUT_GUIDELINES.md)  
Comprehensive timeout recommendations for `run_shell_command` calls. **ESSENTIAL** for reliable execution. Covers:
- Timeout matrix by agent count and complexity
- Task-specific timeout recommendations
- Dynamic timeout calculation strategies
- Progressive timeout and monitoring approaches

## 🎯 When to Read These References

### Before Writing Scripts
Read **SUBAGENT_GUIDELINES.md** to understand:
- Proper temporary directory usage
- File safety practices
- Cleanup strategies

### Before Running Scripts  
Read **TIMEOUT_GUIDELINES.md** to set:
- Appropriate timeouts for task complexity
- Buffer amounts for reliability
- Progressive timeout strategies

### When Debugging Issues
Both documents help with:
- Identifying timeout-related failures
- Fixing file permission problems
- Optimizing performance bottlenecks
- Handling partial agent failures

## 📖 Integration with Main Skill

The main [SKILL.md](../SKILL.md) references these documents when needed:
- Basic guidelines embedded in main skill
- Detailed guidance loaded from references as needed
- Progressive disclosure keeps main skill lean

## 🔍 Quick Reference

### Safe Temp Directory Pattern
```bash
TEMP_DIR="/tmp/subagent_task_$(date +%s)"
mkdir -p "$TEMP_DIR"
```

### Minimum Recommended Timeouts
- **2-4 agents, simple tasks**: 180-300 seconds
- **5-10 agents, medium tasks**: 300-600 seconds  
- **Complex workflows**: 600-900 seconds
- **Large codebases**: 900-1800 seconds

### Always Include in Scripts
- `YOLO_MODE=1` for automation
- `MINI_SANDBOX=0` for file access
- `MAX_RETRIES=10` for reliability
- Unique temp directories with timestamps
- Cleanup functions and strategies

These reference materials provide the detailed guidance needed for safe, reliable subagent execution.