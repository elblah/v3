# Analysis: Council vs Ralph Wiggum
## Two approaches to "keep AI working until task is complete"

**Date**: 2025-12-28  
**Context**: Porting council feature from TypeScript to Python v3

---

## Executive Summary

Two different approaches to ensure AI works continuously until task completion:

| Aspect | Council (TypeScript) | Ralph Wiggum (Claude Code) |
|---------|----------------------|----------------------------|
| **Approach** | Multi-expert review + voting | Single-actor self-referential loop |
| **Trigger** | `/council --auto <spec>` | `/ralph-loop "<prompt>"` |
| **Decision** | Council members vote (unanimous) | Promise phrase detection or max iterations |
| **Philosophy** | "Team of experts review work" | "Keep trying until success" |
| **Complexity** | High (multiple members, consensus) | Low (single prompt, repeat) |
| **Token Cost** | High (each member queries AI) | Low (same prompt repeated) |
| **Validation** | Multi-perspective verification | Self-correction through iteration |
| **Stop Condition** | All members vote FINISHED | Promise detected or max iterations |

---

## Ralph Wiggum Analysis

### Core Concept

**"Ralph is a Bash loop"** - Simple `while true` that repeatedly feeds the AI the same prompt.

### How It Works

```
1. User: /ralph-loop "Build a REST API" --completion-promise "COMPLETE" --max-iterations 20

2. AI: Implements API (iteration 1)

3. AI: Tries to exit

4. Stop Hook (stop-hook.sh):
   - Blocks exit
   - Reads AI's last output
   - Checks for <promise>COMPLETE</promise> tag
   - If NOT found → feeds SAME PROMPT back (iteration 2)
   - If found → allows exit

5. AI: Continues implementation (iteration 2)
   - Sees previous work in files
   - Sees git history
   - Self-corrects and improves

6. Repeat until promise detected or max iterations reached
```

### Key Mechanisms

#### 1. State File (`.claude/ralph-loop.local.md`)
```yaml
---
active: true
iteration: 1
max_iterations: 20
completion_promise: "COMPLETE"
started_at: "2025-12-28T10:00:00Z"
---

Build a REST API for todos. Requirements: CRUD operations, tests, validation.
```

#### 2. Stop Hook (`hooks/stop-hook.sh`)
- Intercepts Claude's exit attempts
- Parses state file
- Reads last assistant message from transcript
- Checks for completion promise tag: `<promise>COMPLETE</promise>`
- If promise not found: blocks exit, feeds prompt back
- If promise found or max iterations: allows exit

#### 3. Promise Detection
```bash
# Extract text from <promise> tags (multiline support)
PROMISE_TEXT=$(echo "$LAST_OUTPUT" | perl -0777 -pe 's/.*?<promise>(.*?)<\/promise>.*/$1/s')

# Exact string comparison (not pattern matching)
if [[ "$PROMISE_TEXT" = "$COMPLETION_PROMISE" ]]; then
  echo "✅ Complete - allowing exit"
  exit 0
fi
```

### Features

#### Pros
1. **Simplicity**: Single command, single prompt, repeat until done
2. **Low token cost**: Same prompt repeated, no multiple AI calls
3. **Self-referential**: AI sees its own work in files and git history
4. **Automatic verification**: Can integrate with tests, linters
5. **Easy to interrupt**: `--max-iterations` as safety net
6. **No external dependencies**: Uses Claude Code's stop hook API

#### Cons
1. **No external validation**: Only AI judges its own completion
2. **Risk of premature exit**: AI might claim completion when not done
3. **Limited perspective**: Single viewpoint, no diverse expert opinions
4. **Relies on AI honesty**: Must output promise only when genuinely true
5. **Infinite loop risk**: If promise never becomes true, runs forever (unless limited)
6. **No strategic guidance**: No expert advice, just "keep trying"

### When It Works Well

**Good for:**
- Well-defined tasks with clear success criteria
- Tasks requiring iteration and refinement (e.g., getting tests to pass)
- Greenfield projects where you can walk away
- Tasks with automatic verification (tests, linters)
- Simple implementation tasks with binary completion

**Not good for:**
- Tasks requiring human judgment or design decisions
- Complex multi-faceted requirements
- Tasks with subjective completion criteria
- Production debugging
- Architectural decisions

### Real-World Results (from README)
- Generated 6 repositories overnight (YC hackathon)
- $50k contract completed for $297 in API costs
- Created entire programming language ("cursed") over 3 months

---

## Council Analysis

### Core Concept

**"Team of experts review and vote"** - Multiple AI personas (council members) review AI's work and vote on completion.

### How It Works

```
1. User: /council --auto "Build a REST API for todos. Requirements: CRUD, validation, tests."

2. AI: Implements API (iteration 1)

3. Auto-Council Trigger:
   - After AI completes, auto-council activates
   - Council members review implementation against spec

4. Council Members (e.g., 5 experts):
   - Code Reviewer: Checks code quality, bugs, best practices
   - Security Expert: Checks vulnerabilities, auth, validation
   - UX Designer: Checks usability, error handling
   - Simplicity Advocate: Checks over-engineering, MVP
   - Spec Validator: Checks spec compliance

5. Each Member:
   - Receives full context (messages, files, spec)
   - Provides opinion (under 300 words)
   - Votes: IMPLEMENTATION_FINISHED or IMPLEMENTATION_NOT_FINISHED

6. Consensus Logic:
   - Unanimous FINISHED = task complete, spec cleared
   - Any NOT_FINISHED = AI receives feedback, tries again

7. AI: Re-implements with feedback (iteration 2)

8. Repeat until unanimous FINISHED
```

### Key Mechanisms

#### 1. Council Members (`.aicoder/council/*.txt`)
```markdown
## COUNCIL_MEMBER_PROFILE
You are a Code Quality Expert.

Role:
- Review code for bugs and best practices
- Check adherence to standards
- Identify potential issues

<MANDATORY_VOTING_RULE>
You MUST end your response with EXACTLY ONE of these lines:
- IMPLEMENTATION_FINISHED
- IMPLEMENTATION_NOT_FINISHED

Vote based on actual implementation evidence.
No postponing, no delays. Make decision now.
</MANDATORY_VOTING_RULE>
```

#### 2. Council Service (`council-service.ts`)
- Loads members from `~/.config/aicoder-mini/council/` or `.aicoder/council/`
- Queries each member separately (no tool access to prevent hallucination)
- Parses votes from last line of each opinion
- Enforces unanimous approval logic

#### 3. Auto-Council Integration
```typescript
// After AI completes implementation
if (autoCouncilEnabled && hasSpec()) {
  // Trigger council review
  nextPrompt = "/council --auto-continue";

  // Council members review:
  // 1. All vote FINISHED → clear spec, complete
  // 2. Any vote NOT_FINISHED → AI receives feedback, continues
}
```

### Features

#### Pros
1. **Multi-perspective validation**: Different experts check different aspects
2. **Unanimous approval required**: Must satisfy all requirements
3. **Expert guidance**: Each member provides specific feedback
4. **Quality assurance**: Security, UX, code quality all checked
5. **Reduced premature completion**: Multiple votes prevent false positives
6. **Configurable**: Add/remove members, create custom councils

#### Cons
1. **High token cost**: Each council member queries AI separately
2. **Complexity**: Multiple moving parts (members, voting, consensus)
3. **Slower iteration**: Must wait for all members to respond
4. **Risk of infinite loop**: Members might always reject (mitigation: max iterations)
5. **Configuration overhead**: Need to create and maintain council members
6. **Context duplication**: Each member receives full context

### When It Works Well

**Good for:**
- Complex multi-faceted requirements
- Tasks requiring quality assurance (security, UX, testing)
- Production-grade implementations
- Tasks with diverse concerns (performance, maintainability, security)
- Specifications with clear acceptance criteria

**Not good for:**
- Simple tasks (overkill)
- Quick prototyping (too slow)
- Tasks with subjective/ambiguous requirements
- Low-stakes projects
- Situations requiring fast turnaround

---

## Architectural Comparison

### Loop Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Ralph Wiggum (Self-Referential Loop)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐                                                              │
│  │  Prompt  │ ──────────────────────────────────────┐                        │
│  └────┬─────┘                                      │                        │
│       │                                             ▼                        │
│       ▼                                    ┌──────────────┐                │
│  ┌─────────────┐                           │   Stop Hook  │                │
│  │ AI Execute  │                           └──────┬───────┘                │
│  └──────┬──────┘                                  │                         │
│         │                               Promise NOT found?                        │
│         ▼                                       │                          │
│  ┌─────────────┐                                │                         │
│  │ Files/Git   │ ◄───────┐                     │                         │
│  └─────────────┘         │                     ▼                         │
│                          │              ┌──────────────┐                    │
│                          │              │ Block Exit   │                    │
│                          │              │ Feed Prompt  │                    │
│                          │              └──────┬───────┘                    │
│                          │                     │                           │
│                          │                     └─────────────────────┐      │
│                          │                                           │      │
│                          ▼                                           ▼      │
│                    ┌─────────────┐                            ┌─────────────┐   │
│                    │  Continue   │                            │   Allow     │   │
│                    │  (next iter)│                            │   Exit      │   │
│                    └──────┬──────┘                            └─────────────┘   │
│                           │                                                        │
└───────────────────────────┴────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Council (Expert Review Loop)                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐                                                              │
│  │   Spec    │ ──────────────────────────────────────┐                        │
│  └────┬─────┘                                      │                        │
│       │                                             ▼                        │
│       ▼                                    ┌──────────────┐                │
│  ┌─────────────┐                           │ AI Execute   │                │
│  │ AI Execute  │                           └──────┬───────┘                │
│  └──────┬──────┘                                  │                         │
│         │                                          │                         │
│         ▼                                          ▼                         │
│  ┌─────────────┐                            ┌──────────────┐                │
│  │   Files    │                            │Auto-Council  │                │
│  └─────────────┘                            │Triggered     │                │
│         │                                  └──────┬───────┘                │
│         │                                         │                         │
│         ▼                                         ▼                         │
│  ┌─────────────┐     ┌──────────────┐    ┌──────────────┐              │
│  │   Member 1  │     │   Member 2   │    │   Member N   │              │
│  │ (Code Review)│     │  (Security)   │    │   (Spec)     │              │
│  └──────┬──────┘     └──────┬───────┘    └──────┬───────┘              │
│         │                    │                   │                        │
│         └────────────────────┴───────────────────┘                        │
│                              │                                          │
│                              ▼                                          │
│                    ┌─────────────────┐                                   │
│                    │  Vote Consensus │                                   │
│                    └───────┬─────────┘                                   │
│                            │                                              │
│              ┌─────────────┴─────────────┐                                │
│              │                           │                                │
│              ▼                           ▼                                │
│    ┌─────────────────┐         ┌─────────────────┐                          │
│    │ All FINISHED    │         │ Any NOT_FINISHED│                          │
│    │ Clear Spec      │         │ AI Receives     │                          │
│    │ Task Complete   │         │ Feedback        │                          │
│    └─────────────────┘         └───────┬─────────┘                          │
│                                       │                                        │
└───────────────────────────────────────┴────────────────────────────────────────┘
```

### Data Flow

#### Ralph Wiggum
```
User Prompt → AI → Files/Git → Stop Hook → Promise Check?
  ↓ No (not done)                          ↓ Yes (done)
Feed prompt back ────────────────────→ Allow exit
```

#### Council
```
Spec → AI → Files → Council Members (N experts)
  ↓                    ↓
  └── Consensus? ──────┘
        ↓ Yes           ↓ No
    Clear Spec      Feedback → AI
```

---

## Critical Design Decisions

### Decision 1: Who Judges Completion?

| Approach | Judge | Pros | Cons |
|----------|-------|------|------|
| Ralph | AI self-judges | Fast, low token cost | Subjective, prone to premature completion |
| Council | Multiple AI experts | Multi-perspective, rigorous | High token cost, slower |

**Recommendation**: Council for production, Ralph for prototyping/experiments

---

### Decision 2: How to Stop?

| Approach | Stop Condition | Flexibility | Safety |
|----------|----------------|------------|--------|
| Ralph | Promise detected OR max iterations | Promise can be any text | Max iterations prevents infinite loop |
| Council | Unanimous FINISHED OR max iterations | Must modify members to change | Same safety mechanism |

**Recommendation**: Both require max iterations as safety net

---

### Decision 3: Context Management

| Approach | Context per Iteration | Perspective |
|----------|----------------------|-------------|
| Ralph | Same prompt, growing file/git history | Self-referential |
| Council | Fresh context each iteration (optional) | Independent review |

**Recommendation**: Council's fresh context prevents "getting stuck" on previous errors

---

### Decision 4: Token Efficiency

| Approach | Token Cost | Scaling | Efficiency |
|----------|------------|---------|------------|
| Ralph | Low (prompt repeated) | O(1) | High |
| Council | High (N members × prompt) | O(N) | Low |

**Recommendation**: Ralph for large tasks, Council for critical quality

---

## Integration Possibilities

### Hybrid Approach: Ralph + Council

Combine the best of both worlds:

```
1. User: /ralph-council "Build REST API" --max-iterations 10 --council "auto"

2. AI: Implements (Ralph loop, iteration 1-3)

3. After 3 iterations (or when AI reports progress):
   - Trigger council review (instead of just continuing Ralph)

4. Council: Reviews, votes
   - If unanimous FINISHED: complete
   - If any NOT: Ralph continues with council feedback

5. Repeat until max iterations or council unanimous FINISHED
```

**Benefits**:
- Speed of Ralph for initial iterations
- Quality assurance of Council for final validation
- Council feedback guides Ralph's self-correction

**Implementation**:
```
/ralph-loop "Build API" --council-every N --max-iterations 20

# Council reviews every N iterations
# Provides guidance, ensures quality
```

---

### Adaptive Approach: Dynamic Mode Switching

```
1. Start with Ralph (fast, low cost)
2. Monitor progress (files changed, tests passing)
3. If stuck after X iterations → switch to Council
4. Council identifies blockers, provides guidance
5. Switch back to Ralph with Council feedback
```

**Benefits**:
- Best of both: speed when possible, guidance when stuck
- Reduces overall token cost (Council only when needed)
- Prevents infinite loops (Council detects when impossible)

---

## Python Porting Considerations

### Implementing Ralph Wiggum in Python v3

**Requirements**:
1. Stop hook mechanism (need to integrate with main loop)
2. State file management (`.claude/ralph-loop.local.md`)
3. Promise detection (parse AI's last output)
4. Max iterations enforcement

**Integration points**:
- `aicoder/core/aicoder.py` - Main loop
- `aicoder/core/session_manager.py` - Post-processing hook
- `.claude/ralph-loop.local.md` - State file

**Pseudocode**:
```python
class RalphLoopManager:
    def __init__(self):
        self.state_file = ".claude/ralph-loop.local.md"
        self.active = False
        self.iteration = 0
        self.max_iterations = 0
        self.completion_promise = None
        self.prompt = None
    
    def start(self, prompt: str, max_iterations: int = 0,
              completion_promise: str = None) -> None:
        # Create state file
        self.prompt = prompt
        self.max_iterations = max_iterations
        self.completion_promise = completion_promise
        self.active = True
        self.iteration = 1
    
    def should_continue(self, ai_output: str) -> bool:
        """Check if loop should continue"""
        # Check max iterations
        if self.max_iterations > 0 and self.iteration >= self.max_iterations:
            return False
        
        # Check for completion promise
        if self.completion_promise:
            promise_text = self._extract_promise(ai_output)
            if promise_text == self.completion_promise:
                return False
        
        # Continue loop
        self.iteration += 1
        return True
    
    def get_next_prompt(self) -> str:
        """Get same prompt for next iteration"""
        return self.prompt
    
    def cancel(self) -> None:
        """Cancel active loop"""
        self.active = False
        self.state_file.unlink(missing_ok=True)

# Integration in AICoder.run()
def run(self) -> None:
    ralph = RalphLoopManager()
    
    while self.is_running:
        # Check if Ralph loop is active
        if ralph.active:
            user_input = ralph.get_next_prompt()
        else:
            user_input = self.input_handler.get_user_input()
        
        # ... process AI response ...
        
        # Check if Ralph should continue
        if ralph.active:
            if not ralph.should_continue(ai_output):
                ralph.cancel()
                continue
```

---

### Implementing Council in Python v3

**Requirements**:
1. CouncilService (already planned)
2. Member loading from `.aicoder/council/`
3. Opinion gathering and voting logic
4. Auto-council trigger after AI completion

**Integration points**:
- `aicoder/core/aicoder.py` - Auto-council support
- `aicoder/core/session_manager.py` - Trigger after processing
- `aicoder/core/council_service.py` - Core service (already planned)

**Pseudocode** (from existing plan):
```python
class CouncilService:
    # (as already planned in COUNCIL_IMPLEMENTATION_PLAN.md)
    pass

class AutoCouncilManager:
    def __init__(self, council_service: CouncilService):
        self.council = council_service
        self.enabled = False
    
    def trigger_if_needed(self, ai_output: str) -> Optional[str]:
        """Trigger council review if spec is loaded"""
        if not self.enabled or not CouncilService.has_spec():
            return None
        
        # Trigger council review
        return "/council --auto-continue"

# Integration in AICoder.run()
def run(self) -> None:
    auto_council = AutoCouncilManager(self.council_service)
    
    while self.is_running:
        user_input = self.get_next_prompt() or self.input_handler.get_user_input()
        
        # ... process AI response ...
        
        # Check auto-council trigger
        if next_prompt := auto_council.trigger_if_needed(ai_output):
            self.set_next_prompt(next_prompt)
```

---

## Recommendations

### For Python v3 Port

**Option 1: Port Council Only**
- Pros: Matches existing TypeScript architecture, proven approach
- Cons: High token cost, complexity

**Option 2: Port Ralph Only**
- Pros: Simpler, lower token cost, easier to implement
- Cons: No multi-perspective validation, prone to premature completion

**Option 3: Port Both + Hybrid**
- Pros: Flexibility, best of both worlds, use cases for each
- Cons: More code to maintain, user complexity

**Recommended**: **Option 3 (Port Both + Hybrid)**

**Rationale**:
1. Council for production-quality work (security, testing, UX)
2. Ralph for rapid prototyping/experiments (speed, low cost)
3. Hybrid mode: Ralph for iterations, Council for validation
4. User can choose based on task complexity and time constraints

### Implementation Priority

1. **Phase 1**: Implement Ralph Wiggum (simpler, immediate value)
   - Stop hook mechanism
   - State file management
   - Promise detection

2. **Phase 2**: Implement Council (existing plan)
   - CouncilService
   - Member loading
   - Voting logic

3. **Phase 3**: Integrate and Hybrid Mode
   - `/ralph-council` command
   - Council triggers after N Ralph iterations
   - Council feedback guides Ralph iterations

4. **Phase 4**: Polish and Documentation
   - Examples for both modes
   - Decision guide (when to use which)
   - Performance optimization

---

## Comparison Summary

| Aspect | Ralph Wiggum | Council | Hybrid |
|---------|--------------|---------|---------|
| **Complexity** | Low | High | Medium |
| **Token Cost** | Low | High | Medium |
| **Quality** | Self-judged | Multi-expert | Council-guided |
| **Speed** | Fast | Slow | Medium |
| **Use Case** | Prototyping | Production | Flexible |
| **Completion** | Promise-based | Unanimous vote | Council-veto |
| **Best For** | Simple, fast tasks | Complex, critical | All tasks |

---

## Conclusion

Both approaches solve the same problem ("keep AI working until task is complete") through different philosophies:

- **Ralph Wiggum**: "Keep trying, you'll get there eventually" (perseverance)
- **Council**: "Team of experts will verify your work" (validation)

For the Python v3 port, I recommend implementing **both** with a hybrid mode:

1. **Ralph** for speed and efficiency during initial iterations
2. **Council** for quality assurance and multi-perspective validation
3. **Hybrid** for best balance (Ralph iterations + Council validation)

This gives users maximum flexibility while maintaining quality and efficiency.

---

**End of Analysis**
