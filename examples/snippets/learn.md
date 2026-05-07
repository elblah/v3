<system-reminder>
LEARN MODE ACTIVE:

Review the current conversation and update skills. Be ACTIVE — if the user specified what to learn, focus on that. If not, scan for something worth persisting.

What to capture:
- User corrections about your style, tone, format, or workflow
- Non-trivial techniques, workarounds, debugging paths
- Project conventions, tool quirks, architecture decisions
- Anything the user explicitly asked to remember

Rules:
1. Check existing skills first (both local and global). If a skill already covers this territory, PATCH it. Do not create duplicates.
2. Write to local dir only: .aicoder/skills/<skill-name>/SKILL.md — you cannot write to global skills.
3. Local overrides global: if you patch a skill that exists globally, create the local version with the update. It will override the global one.
4. Name at class level: debugging, build-process, code-style — NOT fix-auth-bug-tuesday or pr-42.
5. SKILL.md format:
   ---
   name: skill-name
   description: One-line description (max 1024 chars)
   ---
   # Skill Title
   Full instructions here...
6. Optional subdirectories: references/, templates/, scripts/ — use if the skill needs supporting files.
7. Do not over-learn: trivia, one-off facts, or things obvious from the codebase don't need skills.

If nothing in the conversation merits a skill, say so and stop. Don't force it.
</system-reminder>
