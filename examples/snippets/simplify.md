<system-reminder>
CODE SIMPLIFICATION MODE ACTIVE:

Apply these techniques to make code clearer and more maintainable:

**Control Flow:**
- Use guard clauses and early returns - handle edge cases first
- Flatten nested conditionals - extract or invert logic
- Remove unnecessary `else` after `return`/`break`/`continue`/`raise`
- Aim for minimal indentation (1-3 levels ideal, avoid 4+)

**Boolean Logic:**
- Simplify complex boolean expressions
- Remove double negatives (`if not not x` → `if x`)
- Consider named boolean variables for complex conditions (but avoid single-use noise)
- Use short-circuit evaluation (`and`/`or`) effectively

**Structure:**
- Extract complex blocks into well-named helper functions (but don't fragment logic)
- Replace long if-elif chains with dict/map lookups
- Use comprehensions over verbose loops when clearer
- Remove dead code and unreachable branches

**Clean-up:**
- Remove unused variables, parameters, imports
- Replace magic numbers/strings with named constants
- Remove redundant conditions (`if x == True` → `if x`)
- Merge duplicate code blocks (but avoid over-abstraction - sometimes duplication is clearer)

**Naming:**
- Use descriptive function/variable names - they eliminate need for comments
- Reduce parameter count - split functions with many parameters
- Prefer clear over clever

**Language-Agnostic:**
- Use destructuring/unpacking where available
- Use string interpolation over concatenation
- Use membership tests: `x in collection`
- Prefer built-ins for readability (but manual loops for performance-critical code)

**When NOT to simplify:**
- Inherently complex algorithms (crypto, parsing, math) - comment instead
- When simplification adds more abstraction than it removes
- When it makes the code less familiar to your team

**Rule:** Code should be obvious on first read. If not, simplify or comment.
</system-reminder>
