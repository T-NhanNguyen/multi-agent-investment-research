---
trigger: always_on
---

## 1. Philosophy

Sustainable engineering over vibe coding. Code must endure, not merely function. Specification is the contract between human intent and AI implementation. Engineering discipline enables sustainable velocity; its absence creates compounding technical debt.

Human roles: **Curator** (select and frame problems), **Validator** (design verification), **Architect** (maintain system coherence). AI automates generation; architectural thinking remains human.

Prioritize **efficiency** (value toward agent goals) over raw effectiveness. Favor correct and reliable over micro-optimizations.

## 2. Specification and Context

**CLAUDE.md** serves as the primary context contract. Place in project root with: common commands, core files and utilities, code style with explicit examples, testing procedures, and workflow conventions. Load automatically at session start.

**README-driven development**: Treat README.md as the first artifact, not an afterthought. Include architecture overview, setup commands, conventions, and pattern documentation. Update continuously.

**Modular decomposition**: Break complex objectives into sequenced, verifiable subtasks. Never use monolithic prompts. Each subtask requires clear inputs, outputs, and verification criteria. Output of one subtask becomes input to the next with explicit handoff points.

**File headers**: Every code file must start with two lines prefixed `ABOUTME: ` describing what the file does. Example:

```python
# ABOUTME: Fetches bulk price data from Yahoo Finance with caching and retry logic
# ABOUTME: Returns normalized DataFrames for agent consumption
```

## 3. Workflow

**Structure**: Explore -> Plan -> Code -> Commit. Never skip phases.

- **Explore**: Gather information without implementation pressure. Analyze requirements, identify patterns, clarify constraints.
- **Plan**: Produce explicit implementation outline with architectural decisions, component breakdown, and validation criteria. Review plan before coding.
- **Code**: Implement with active monitoring. Review generated code for architectural compliance immediately.
- **Commit**: Integrate only after comprehensive validation.

**Test Driven Development (Mandatory)**:

1. Write a failing test that validates desired functionality
2. Run the test to confirm it fails
3. Write only enough code to make the test pass
4. Verify the test passes
5. Refactor while keeping tests green

**Task tracking**: Never discard tasks without explicit permission from user.

**Memory**: Use the journal frequently to record technical insights, failed approaches, architectural decisions, and user preferences. Search the journal when trying to remember past experiences.

**Permissions**: Stop and ask user for explicit permission when:

- Making exceptions to any rule
- Deleting or significantly restructuring existing code
- Implementing backward compatibility
- Working with uncommitted changes or untracked files (suggest committing first)

## 4. Code Standards

**Naming**:

- Reveal intent, not implementation: `calculateUserRiskScore` not `ZodRiskValidator`
- No temporal context: `RiskCalculator` not `NewRiskCalculator` or `LegacyCalculator`
- No implementation details in names: `Tool` not `AbstractToolInterface`, `RemoteTool` not `MCPToolWrapper`
- Single-letter variables: loops and math only (i, j, k)
- Underscore prefix for niche helper functions: `_transformData`

**Comments**:

- Explain only non-obvious logic or complex algorithms
- Explain what the code does or why it exists, never how it's "better" than before
- Never document old behavior or changes in comments
- Never add instructional comments telling developers what to do
- Preserve existing comments unless provably false

**DRY with pragmatism**:

- Extract repeated logic to named functions or classes
- Avoid over-abstraction that hurts clarity
- Centralize agent patterns: retry logic, logging, schema validation
- Fetch Big Once, Cache Computed, Render only Needed

**Aspect-Oriented Programming (AOP)**.

- "Keep the pruner code focused on pruning, and let the monitor focus on counting."

**Constants and Configuration**:

- UPPER_CASE for constants
- Use enums for related constant values
- Reference global config or .env directly, avoid class-level aliases redundant with global constants

**Bulk and Efficiency**:

- Prefer batch APIs over single operations (critical for token efficiency)
- Implement caching where appropriate
- Example: bulk price fetch over individual ticker calls

**Error Handling**:

- Never swallow exceptions silently
- Use contextual logs including relevant identifiers (ticker, timestamp, attempt count)
- Return sensible defaults (None, empty dict) or custom exceptions for agent retry logic
- Implement retry/backoff/circuit-breakers as needed
- ISO standardization for all data points

**Validation and Security**:

- Validate external inputs early
- Sanitize if required
- Never log or expose secrets
- Use type hints (Python) or interfaces (TypeScript)

**Agentic Interface Design**:

- Functions should serve as clear LLM tools: comprehensive docstrings, typed parameters, deterministic outputs
- Return structured data (dicts, DataFrames, JSON)
- Track costs (token counts, API calls)

## 5. Architecture

**Single Responsibility**: Each component encapsulates one well-defined purpose. Capability ownership eliminates ambiguity about where functionality belongs.

**API-First Design**: Define explicit interfaces before implementation. Specify behavioral contracts: preconditions, postconditions, errors, performance characteristics. Use consistent resource naming, response formats, and versioning.

**Event-Driven Patterns**: Use events and message-passing for loose coupling. Enables independent component evolution and accommodates AI processing latency.

**Interface Contracts**: Enforce schema validation at system boundaries (JSON Schema, OpenAPI). Fail fast on malformed data. Informative error responses without internal exposure.

**Boundaries**:

- Always: Safe, routine operations (tests, conventions, logging)
- Ask First: High-impact changes (DB schema, dependencies, CI/CD, architectural changes)
- Never: Prohibited operations (commit secrets, edit vendor directories, remove failing tests without approval)

## 6. Debugging and Quality Assurance

**Systematic Debugging (Mandatory)**:

Phase 1: Root Cause Investigation

- Read error messages carefully; they often contain the solution
- Reproduce the issue consistently before investigating
- Check recent changes (git diff, commits)

Phase 2: Pattern Analysis

- Find working examples in the codebase
- Compare against reference implementations
- Identify differences between working and broken code
- Understand dependencies

Phase 3: Hypothesis and Testing

- Form a single, clear hypothesis
- Make the smallest possible change to test it
- Verify results before continuing
- If wrong, form a new hypothesis; do not add more fixes

Phase 4: Implementation

- Always have the simplest possible failing test case
- Never add multiple fixes at once
- Never claim to implement a pattern without reading it completely
- Always test after each change
- If first fix fails, stop and re-analyze

**Quality Standards**:

- All test failures are your responsibility, even if not your fault
- Never delete failing tests; raise the issue with User
- Tests must cover all functionality
- Never write tests that test mocked behavior
- Never use mocks in end-to-end tests; use real data and APIs
- Never ignore system or test output; logs contain critical information
- Test output must be pristine to pass

**Mutation and Property Testing**:

- Use mutation testing to validate test suite effectiveness
- Use property-based testing for specification adherence (invariants, not just examples)
- Use contract testing for API boundaries
