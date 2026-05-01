<system-reminder>
MIKADO MODE ACTIVE:

For refactoring complex legacy code without getting stuck.

CORE PRINCIPLE: Map dependencies, work from leaves inward.

1. DRAW GOAL GRAPH
   - Main goal at top/center
   - When blocked: what's missing becomes a subgoal
   - Tree structure of prerequisites

2. TIME-BOX ATTEMPTS
   - 5-15 min per attempt
   - Small, safe steps

3. IF BLOCKED:
   - Revert changes immediately
   - Identify what's missing
   - Write new subgoal
   - Loop back

4. IF SUCCESS:
   - Commit
   - Move to next unchecked subgoal
   - Work from leaves inward

EXAMPLE GRAPH:
"Upgrade ORM"
├── "Extract .query() calls"
│   └── "Find all .query() usages"
├── "Extract .dump() calls"
│   └── "Standardize call patterns"
└── "Update dependency"

Prevents quicksand: fix A, break B, fix B, break C.
Loop until goal achieved. Always leave code compiling.
</system-reminder>