<system-reminder>
TRACER BULLET MODE ACTIVE (from Pragmatic Programmer):

When requirements are vague or system is uncertain, build end-to-end slices.

CORE PRINCIPLE: Build thin, working slice through ALL layers - not a prototype.

1. IDENTIFY RISKY AREA
   - Choose biggest uncertainty or risk
   - Could be tech, architecture, or unknown requirements

2. BUILD SLICE END-TO-END
   - UI → business logic → data → API
   - Must be working, not placeholder
   - Lean but complete code

3. GET FEEDBACK
   - Show users/stakeholders
   - "Is this hitting the target?"
   - Adjust trajectory based on response

4. REPEAT
   - Next slice builds on proven skeleton
   - Team can parallelize (skeleton + polish)

DIFFERENCE FROM PROTOTYPES:
- Prototypes: explore, learn, throw away
- Tracer bullets: explore, learn, KEEP (it's the skeleton)

Loop until system complete. No over-engineering upfront.
</system-reminder>