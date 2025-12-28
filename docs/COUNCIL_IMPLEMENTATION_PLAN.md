# Council Feature Implementation Plan
## Porting from TypeScript to Python v3

**Status**: Planning Phase  
**Complexity**: High  
**Priority**: Medium-High  

---

## Executive Summary

Port the council feature from the TypeScript version (`../tsv/src/core/council.ts`) to Python v3 as a plugin. The council provides expert opinions on AI work and an auto-mode that ensures tasks are truly complete before declaring "done".

**Two Modes**:
1. **Normal Council**: `/council [message]` - Get expert opinions/advice
2. **Auto Council**: `/council --auto <spec>` - Auto-review loop until task complete

---

## Architecture Overview

### Components

1. **CouncilService** (`aicoder/core/council_service.py`)
   - Core service for council operations
   - Member loading, opinion gathering, consensus
   - Spec management for auto-mode
   - Unanimous approval logic

2. **CouncilPlugin** (`plugins/05_council.py`)
   - User-facing `/council` command
   - Subcommands: `current`, `accept`, `clear`, `list`, `list-members`, `edit`, `enable`, `disable`
   - Auto-mode triggers (`--auto`, `--auto-continue`)
   - Member filtering (`--members <filter>`)

3. **Auto-Council Integration**
   - Modified `aicoder/core/aicoder.py` - Auto-council support
   - Modified `aicoder/core/session_manager.py` - Trigger auto-council

4. **Example Council Members**
   - Auto-mode: `*_auto.txt` files in `.aicoder/council/` or `~/.config/aicoder/council/`
   - Normal mode: `*.txt` files (without `_auto` suffix)
   - Installation script

---

## Phase 1: Core Council Service (Foundation)

### Deliverables
- `aicoder/core/council_service.py` - Core service (~400 lines)
- `plugins/05_council.py` - Plugin (~500 lines)

### Key Classes

#### CouncilMember
```python
@dataclass
class CouncilMember:
    name: str
    prompt: str
    is_auto_member: bool = False
```

#### CouncilSession
```python
@dataclass
class CouncilSession:
    original_messages: List[Dict[str, Any]]
    opinions: Dict[str, str] = field(default_factory=dict)
    consensus_achieved: bool = False
    final_plan: Optional[str] = None
```

#### CouncilService
```python
class CouncilService:
    # Spec management (static for persistence)
    _current_spec: Optional[str] = None
    _current_spec_file: Optional[str] = None
    _last_successful_council_dir: Optional[str] = None
    
    def __init__(self, ai_processor: AIProcessor)
    async def start_session(self, messages: List[Dict[str, Any]]) -> None
    async def load_members(self, filters: List[str] = None, auto_mode: bool = False) -> List[CouncilMember]
    async def get_member_opinion(self, member: CouncilMember, user_request: str) -> str
    async def get_member_consensus(self) -> str
    async def get_consensus(self, moderator: CouncilMember) -> str
    async def get_direct_expert_opinions(self) -> str
    def get_session_status(self) -> Optional[CouncilSession]
    def clear_session(self) -> None
    
    # Spec management (static methods)
    @staticmethod
    def load_spec(spec_content: str, spec_file: str) -> None
    @staticmethod
    def has_spec() -> bool
    @staticmethod
    def get_current_spec() -> Optional[str]
    @staticmethod
    def get_current_spec_file() -> Optional[str]
    @staticmethod
    def clear_spec() -> None
```

### Implementation Details

#### Member Loading
- Check `.aicoder/council/` first (project-specific)
- Then check `~/.config/aicoder/council/` (global)
- Cache directory for auto-mode consistency
- Auto-mode: Load only `*_auto.txt` files
- Normal mode: Load `*.txt` files excluding `*_auto.txt`

#### Opinion Gathering
- Use AIProcessor for queries (reuses existing infrastructure)
- **Critical**: Exclude tools from council queries (no tool definitions)
- Pass member profile as system prompt
- Include spec in auto-mode queries
- Include recent context (last 20 messages)

#### Voting Logic
- Parse `IMPLEMENTATION_FINISHED` or `IMPLEMENTATION_NOT_FINISHED` from last line
- Unanimous `IMPLEMENTATION_FINISHED` = task complete
- Any `IMPLEMENTATION_NOT_FINISHED` = continue with feedback
- Fallback: If pattern not recognized, assume `IMPLEMENTATION_NOT_FINISHED`

#### Spec Management
- Spec loaded to `.aicoder/current-spec.md` (working copy)
- Original spec file path stored
- Spec cleared when task complete
- Static methods for persistence across sessions

---

## Phase 2: Auto-Council Integration

### Deliverables
- Modified `aicoder/core/aicoder.py` - Add auto-council support
- Modified `aicoder/core/session_manager.py` - Trigger auto-council

### Key Changes

#### AICoder Class
```python
class AICoder:
    def __init__(self):
        # ... existing code ...
        self.council_service: Optional[CouncilService] = None
        self.next_prompt: Optional[str] = None
        self.auto_council_enabled: bool = False
        self.auto_council_iteration: int = 0
        self.max_auto_council_iterations: int = 10
    
    def initialize(self) -> None:
        # ... existing code ...
        from aicoder.core.council_service import CouncilService
        from aicoder.core.ai_processor import AIProcessor
        ai_processor = AIProcessor(self.streaming_client)
        self.council_service = CouncilService(ai_processor)
    
    def set_next_prompt(self, prompt: str) -> None
    def get_next_prompt(self) -> Optional[str]
    def enable_auto_council(self) -> None
    def disable_auto_council(self) -> None
    def increment_auto_council_iteration(self) -> None
```

#### SessionManager Class
```python
class SessionManager:
    def set_aicoder(self, aicoder: AICoder) -> None
    
    def _handle_post_processing(self, has_tool_calls: bool) -> None:
        # ... existing code ...
        # Check if auto-council should be triggered
        if self.aicoder and self.aicoder.auto_council_enabled:
            if CouncilService.has_spec():
                self.aicoder.set_next_prompt("/council --auto-continue")
```

#### Main Loop (AICoder.run())
```python
def run(self) -> None:
    while self.is_running:
        # ... existing code ...
        
        # Use next_prompt if set (auto-council trigger)
        user_input = self.get_next_prompt() or self.input_handler.get_user_input()
        self.next_prompt = None  # Clear after use
        
        # ... existing processing ...
        
        # Check auto-council iteration limit
        if self.auto_council_enabled:
            if self.auto_council_iteration >= self.max_auto_council_iterations:
                LogUtils.warn("Auto-council max iterations reached")
                self.disable_auto_council()
```

---

## Phase 3: Example Council Members

### Deliverables
- Example council members in `.aicoder/council/` (template)
- Installation script `examples/council/install.sh`

### Auto-Mode Members (`*_auto.txt`)

#### code_reviewer_auto.txt
- Code quality, bugs, best practices
- Vote on implementation completeness
- 300-word limit, concise analysis

#### security_expert_auto.txt
- Security vulnerabilities, best practices
- Input validation, authentication, authorization
- Vote on security requirements

#### ux_designer_auto.txt
- UX, usability, interface design
- User flow, error handling, feedback
- Vote on UX requirements

#### simplicity_advocate_auto.txt
- Simplicity, MVP, over-engineering
- Essential vs. nice-to-have features
- Vote on simplicity

#### spec_validator_auto.txt
- Spec compliance, missing requirements
- Each spec point verified
- Vote on spec completion

### Normal Mode Members (`*.txt`)
- Similar roles but without voting requirements
- Provide advice and recommendations
- Use moderator for synthesis

### Installation Script
```bash
#!/bin/bash
COUNCIL_DIR="$HOME/.config/aicoder/council"
EXAMPLE_DIR="$(dirname "$0")"

mkdir -p "$COUNCIL_DIR"
echo "Installing council members to $COUNCIL_DIR..."
cp "$EXAMPLE_DIR"/*.txt "$COUNCIL_DIR/"
echo "Done!"
```

---

## Phase 4: Configuration and Documentation

### Configuration

#### Environment Variables
- `COUNCIL_ENABLED=1` - Enable/disable council feature (default: enabled)
- `COUNCIL_AUTO_RESET_CONTEXT=1` - Context reset behavior (default: true)
- `COUNCIL_MAX_MEMBERS=5` - Limit concurrent members (default: no limit)
- `COUNCIL_MAX_ITERATIONS=10` - Max auto-council iterations (default: 10)
- `COUNCIL_DIR` - Custom council directory

#### Implementation in Config class
```python
class Config:
    @staticmethod
    def council_enabled() -> bool:
        return os.getenv("COUNCIL_ENABLED", "1") == "1"
    
    @staticmethod
    def council_auto_reset_context() -> bool:
        return os.getenv("COUNCIL_AUTO_RESET_CONTEXT", "1") == "1"
    
    @staticmethod
    def council_max_members() -> Optional[int]:
        val = os.getenv("COUNCIL_MAX_MEMBERS")
        return int(val) if val else None
    
    @staticmethod
    def council_max_iterations() -> int:
        return int(os.getenv("COUNCIL_MAX_ITERATIONS", "10"))
    
    @staticmethod
    def council_dir() -> Optional[str]:
        return os.getenv("COUNCIL_DIR")
```

### Documentation

#### docs/COUNCIL.md
- Feature overview
- Normal council usage
- Auto-council usage
- Council member creation guide
- Configuration options

#### docs/AUTO_COUNCIL.md
- Auto-council workflow
- Spec format requirements
- Voting logic explanation
- Troubleshooting

#### docs/COUNCIL_MEMBERS.md
- Member file format
- Voting pattern requirements
- Example members
- Best practices

---

## Phase 5: Polish and Optimization (Optional)

### Performance Optimizations
- Parallel council member queries (async/await)
- Context caching between iterations
- Token usage monitoring

### UX Improvements
- Progress indicator during council review
- Council member selection UI
- Member editing UI
- Member disable/enable UI

### Error Handling
- Member loading errors
- Voting errors
- API errors during council review
- Context overflow handling

---

## Edge Cases and Prevention

### 1. Infinite Loop
**Risk**: Council always rejects implementation
**Prevention**: Max iterations limit, user interrupt (Ctrl+C)

### 2. Council Directory Not Found
**Risk**: User has no council members configured
**Prevention**: Graceful error message, instructions for setup

### 3. Voting Pattern Not Recognized
**Risk**: Member doesn't follow voting format
**Prevention**: Fallback to `IMPLEMENTATION_NOT_FINISHED`, warning message

### 4. Context Overflow During Loop
**Risk**: Multiple iterations blow up context
**Prevention**: Auto-compaction, context reset (default behavior)

### 5. Spec File Corruption
**Risk**: `.aicoder/current-spec.md` missing or corrupted
**Prevention**: Validation on load, graceful error handling

### 6. API Errors During Council
**Risk**: Council member queries fail
**Prevention**: Retry logic, fallback opinions, continue with available data

### 7. Process CWD Change
**Risk**: Working directory changes during auto-mode
**Prevention**: Cache successful council directory

### 8. Member Prompt Injection
**Risk**: Malicious member prompts
**Prevention**: Sanitize member prompts, limit file size

---

## Testing Strategy

### Unit Tests
- `CouncilService.load_members()` - Member loading and filtering
- `CouncilService.parse_vote()` - Voting pattern recognition
- `CouncilService.load_spec()` - Spec management
- Council member prompt building

### Integration Tests
- Normal council workflow
- Auto-council workflow
- Auto-council iteration limit
- Spec loading and clearing
- Member filtering

### Manual Tests
- Install example council members
- Run `/council list-members`
- Run `/council review my code`
- Run `/council --auto "Implement a REST API"`
- Interrupt auto-council with Ctrl+C
- Edit council members with `/council edit`

---

## Implementation Priorities

1. **Phase 1**: Core council service + plugin (Foundation)
2. **Phase 2**: Auto-council integration (Main feature)
3. **Phase 3**: Example council members (Testing)
4. **Phase 4**: Configuration and documentation (Polish)
5. **Phase 5**: Optimization (Nice to have)

---

## Technical Notes

### Tool Exclusion for Council
**Critical**: Council members must NOT receive tool definitions. This prevents hallucinated tool calls and ensures council members only provide advice.

Implementation:
```python
async def get_member_opinion(self, member: CouncilMember, user_request: str) -> str:
    # Build prompt WITHOUT tools
    prompt = f"""
<COUNCIL_MEMBER_PROFILE>
{member.prompt}
</COUNCIL_MEMBER_PROFILE>

User request: "{user_request}"

Recent context:
{self._format_context()}

Provide your opinion. If in auto-mode, vote on the last line:
IMPLEMENTATION_FINISHED
or
IMPLEMENTATION_NOT_FINISHED
"""
    
    opinion = await self.processor.process_messages(
        self.session.original_messages,
        prompt,
        {"excludeTools": True}  # CRITICAL: No tools
    )
```

### Context Reset in Auto-Mode
Default: Context reset each round (fresh perspective)
Configurable: `COUNCIL_AUTO_RESET_CONTEXT=0` to preserve context

### Unanimous Approval Logic
```python
def check_unanimous_approval(self) -> bool:
    """Check if all members voted IMPLEMENTATION_FINISHED"""
    for opinion in self.session.opinions.values():
        vote = self.parse_vote(opinion)
        if vote != 'IMPLEMENTATION_FINISHED':
            return False
    return True
```

### Directory Resolution
```python
def _find_council_dir(self) -> str:
    """Find council directory with project override"""
    # Check project-specific first
    project_dir = Path.cwd() / '.aicoder' / 'council'
    if project_dir.exists():
        return str(project_dir)
    
    # Check config override
    if Config.council_dir():
        return Config.council_dir()
    
    # Default global directory
    return str(Path.home() / '.config' / 'aicoder' / 'council')
```

---

## Timeline Estimate

- Phase 1: 4-6 hours (Core service + plugin)
- Phase 2: 2-3 hours (Auto-council integration)
- Phase 3: 1-2 hours (Example members)
- Phase 4: 1-2 hours (Configuration + docs)
- Phase 5: 2-3 hours (Polish + optimization)

**Total**: 10-16 hours

---

## Dependencies

### Existing Dependencies
- `aicoder.core.ai_processor.AIProcessor` - Council queries
- `aicoder.core.config.Config` - Configuration
- `aicoder.core.command_handler.CommandHandler` - Command registration
- `aicoder.core.plugin_system.PluginSystem` - Plugin infrastructure

### No New Dependencies
- Pure Python stdlib only
- Reuses existing infrastructure

---

## Risks and Mitigations

### Risk 1: Token Usage
Council members can be verbose → Token explosion
**Mitigation**: 300-word limit for auto-mode members

### Risk 2: API Failures
Council member queries fail → Incomplete review
**Mitigation**: Retry logic, fallback opinions

### Risk 3: User Experience
Auto-council loops → User frustration
**Mitigation**: Max iterations, clear progress, interruptible

### Risk 4: Compatibility
TypeScript implementation diverges from Python
**Mitigation**: Reference TypeScript code for logic, adapt to Python architecture

---

## Success Criteria

- [x] Normal council works: `/council [message]`
- [x] Auto-council works: `/council --auto <spec>`
- [x] Auto-continue triggers after AI implementation
- [x] Unanimous approval logic correct
- [x] Spec loads and clears correctly
- [x] Council members load from directory
- [x] Member filtering works: `--members <filter>`
- [x] Subcommands work: `list`, `current`, `accept`, `clear`, `edit`, `enable`, `disable`
- [x] Configuration options work
- [x] Documentation complete

---

## Next Steps

1. Review and approve this plan
2. Start Phase 1 implementation
3. Test incrementally after each phase
4. Gather feedback and iterate
5. Finalize and document

---

**End of Implementation Plan**
