# Claude Development Guidelines for AirBorne

This document provides instructions for Claude (AI assistant) when working on the AirBorne project.

---

## Primary Directive: Follow the Plan

**ALWAYS follow `plan.md`** as the authoritative source of truth for implementation.

- Work through phases sequentially (Phase 0 → Phase 1 → Phase 2 → ...)
- Complete all tasks within a phase before moving to the next
- Do not skip tasks unless explicitly instructed
- Do not deviate from the architecture without discussion

---

## Progress Tracking

### Update plan.md

As you complete tasks, **update `plan.md`** to track progress:

1. **Mark completed tasks** by adding a checkbox:
   ```markdown
   #### 1.1: Implement Event Bus (1 hour) ✅
   **Status**: COMPLETED - 2025-10-12
   ```

2. **Track current task** being worked on:
   ```markdown
   #### 1.2: Implement Message Queue (2 hours) 🚧
   **Status**: IN PROGRESS - Started 2025-10-12
   ```

3. **Add notes** for deviations or important decisions:
   ```markdown
   #### 1.3: Implement Plugin Interface (2 hours)
   **Status**: COMPLETED - 2025-10-12
   **Notes**: Added additional `on_error()` method for error handling
   ```

4. **Update milestones** when reached:
   ```markdown
   ### M1: Core Framework Complete (End of Phase 1) ✅
   **Completed**: 2025-10-15
   **Notes**: All tests passing, ready for Phase 2
   ```

---

## When Unsure: Ask Questions

**DO NOT guess or make assumptions** when uncertain. Instead:

1. **Stop and ask** the user for clarification
2. **Explain the ambiguity** you've encountered
3. **Propose options** if multiple approaches are possible
4. **Wait for confirmation** before proceeding

### Examples of When to Ask

- Unclear requirements in plan.md
- Multiple valid implementation approaches
- Design decision needed (not specified in plan)
- Dependency or library selection
- Configuration format or structure
- User preference for features

### Good Question Format

```
I'm working on [Task X] and encountered [ambiguity/choice].

Options:
1. [Approach A] - [pros/cons]
2. [Approach B] - [pros/cons]

My recommendation: [Approach A] because [reason].

How would you like me to proceed?
```

---

## Phase Completion Assessment

At the **end of each phase**, perform a comprehensive assessment:

### 1. Code Quality Review

Review all code written in the phase:

```markdown
## Phase X Code Quality Assessment

### Code Structure
- [ ] All classes/functions follow single responsibility principle
- [ ] Code is modular and reusable
- [ ] No code duplication (DRY principle)
- [ ] Proper separation of concerns

### Code Style
- [ ] Follows PEP 8 style guide
- [ ] Formatted with Black
- [ ] Type hints on all functions/methods
- [ ] Docstrings on all public APIs
- [ ] Maximum line length: 100 characters

### Error Handling
- [ ] Appropriate exception handling
- [ ] Graceful degradation (no crashes)
- [ ] Meaningful error messages
- [ ] Logging for debugging

### Performance
- [ ] No obvious performance bottlenecks
- [ ] Efficient algorithms used
- [ ] Appropriate data structures
- [ ] Memory usage reasonable

### Maintainability
- [ ] Clear variable/function names
- [ ] Easy to understand logic
- [ ] Well-organized file structure
- [ ] Minimal complexity
```

### 2. Feature Completion Status

Verify all features work as specified:

```markdown
## Phase X Feature Completion

### Success Criteria (from plan.md)
- [x] Criterion 1: Description - **PASS** / FAIL
- [x] Criterion 2: Description - **PASS** / FAIL
- [ ] Criterion 3: Description - PASS / **FAIL** - Reason: [explanation]

### Additional Testing
- Manual testing performed: Yes / No
- Edge cases tested: Yes / No
- Integration with previous phases: Working / Issues

### Known Issues
1. [Issue description] - Severity: High/Medium/Low
2. [Issue description] - Severity: High/Medium/Low

### Blockers
- [ ] None
- [ ] [Blocker description] - Needs: [what's needed to resolve]
```

### 3. Summary Report

Provide a brief summary:

```markdown
## Phase X Completion Summary

**Status**: ✅ Complete / ⚠️ Complete with Issues / ❌ Incomplete

**Completion Date**: YYYY-MM-DD

**Summary**: Brief description of what was accomplished.

**Code Quality**: Excellent / Good / Needs Improvement

**Test Coverage**: All tests passing / Some failures / No tests

**Ready for Next Phase**: Yes / No (if no, explain why)
```

---

## Unit Testing Requirements

**Write unit tests for every component** to ensure correctness.

### Testing Standards

1. **Test Coverage**
   - Aim for >80% code coverage
   - Test all public methods
   - Test edge cases and error conditions
   - Test integration points between plugins

2. **Test Location**
   - Mirror source structure in `tests/` directory
   - Example: `src/airborne/core/event_bus.py` → `tests/core/test_event_bus.py`

3. **Test Naming**
   - Use descriptive test names: `test_event_bus_dispatches_to_subscribers`
   - Follow pattern: `test_[unit]_[scenario]_[expected_result]`

4. **Test Structure**
   ```python
   def test_feature_name():
       """Test description of what is being tested."""
       # Arrange: Set up test data and conditions
       event_bus = EventBus()
       handler_called = False

       def handler(event):
           nonlocal handler_called
           handler_called = True

       # Act: Execute the code being tested
       event_bus.subscribe(TestEvent, handler)
       event_bus.publish(TestEvent())

       # Assert: Verify the expected results
       assert handler_called, "Handler should have been called"
   ```

5. **Use pytest Fixtures**
   ```python
   import pytest

   @pytest.fixture
   def event_bus():
       """Provide a fresh EventBus instance for each test."""
       return EventBus()

   def test_subscription(event_bus):
       # Test using the fixture
       pass
   ```

6. **Mock External Dependencies**
   ```python
   from unittest.mock import Mock, patch

   def test_audio_engine_plays_sound():
       mock_bass = Mock()
       with patch('pybass.BASS_ChannelPlay', mock_bass):
           engine = PyBassAudioEngine()
           engine.play_sound("test.wav")
           mock_bass.assert_called_once()
   ```

### When to Write Tests

- **Before implementation** (TDD): Write test first, then implement
- **During implementation**: Write tests alongside code
- **After implementation**: Verify with tests immediately

**Never move to next task without tests for current task.**

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/core/test_event_bus.py

# Run with coverage
uv run pytest --cov=src/airborne --cov-report=html

# Run with verbose output
uv run pytest -v
```

---

## Documentation Standards

Follow **industry-standard Python documentation** practices to enable auto-generation of developer docs.

### Docstring Format: Google Style

Use **Google-style docstrings** (compatible with Sphinx, pdoc, mkdocs):

```python
def function_name(param1: int, param2: str) -> bool:
    """Brief one-line description of function.

    More detailed description if needed. Explain what the function does,
    not how it does it (that's for comments in the code).

    Args:
        param1: Description of param1. Be specific about type expectations,
            valid ranges, and any constraints.
        param2: Description of param2. Include examples if helpful.

    Returns:
        Description of return value. Explain what it represents and any
        special values (None, empty list, etc.).

    Raises:
        ValueError: When param1 is negative.
        RuntimeError: When external resource is unavailable.

    Examples:
        >>> function_name(42, "test")
        True
        >>> function_name(0, "")
        False

    Note:
        Any important notes, warnings, or usage tips.
    """
    pass
```

### Class Documentation

```python
class ClassName:
    """Brief one-line description of class.

    Longer description explaining the purpose, responsibilities, and
    usage of this class. Explain design decisions if relevant.

    Attributes:
        attr1: Description of public attribute.
        attr2: Description of public attribute.

    Examples:
        >>> obj = ClassName(param=value)
        >>> obj.method()
        'result'

    Note:
        Important usage notes or warnings.
    """

    def __init__(self, param: str):
        """Initialize ClassName.

        Args:
            param: Description of initialization parameter.
        """
        self.attr1 = param
        self._private_attr = None  # Private attrs don't need docstring

    def public_method(self) -> str:
        """Public methods must have full docstrings."""
        pass

    def _private_method(self):
        """Private methods can have brief docstrings."""
        pass
```

### Module Documentation

Every module (`.py` file) should have a module-level docstring:

```python
"""Brief description of module purpose.

This module provides functionality for X. It is part of the Y subsystem
and is typically used for Z purposes.

Typical usage example:
    from airborne.core import module_name

    obj = module_name.ClassName()
    result = obj.method()

Note:
    Any important module-level information.
"""

import statements
...
```

### Type Hints

**Always use type hints** for function signatures:

```python
from typing import List, Dict, Optional, Tuple, Callable, Any

def process_data(
    items: List[str],
    config: Dict[str, Any],
    callback: Optional[Callable[[str], None]] = None
) -> Tuple[int, List[str]]:
    """Process data with type hints."""
    pass
```

### Inline Comments

Use inline comments for **complex logic only**:

```python
# Good: Explains non-obvious logic
# Calculate lift using simplified aerodynamic equation
# L = 0.5 * ρ * v² * S * Cl
lift = 0.5 * air_density * velocity**2 * wing_area * lift_coefficient

# Bad: States the obvious
# Increment counter by 1
counter += 1
```

### Documentation Generation

To generate developer documentation:

```bash
# Using pdoc (recommended)
uv run pdoc --html --output-dir docs src/airborne

# Using Sphinx (alternative)
cd docs
uv run sphinx-build -b html source build
```

### Documentation Checklist

For every file you create or modify:

- [ ] Module-level docstring at top
- [ ] All public classes have docstrings
- [ ] All public methods have docstrings with Args/Returns/Raises
- [ ] Complex algorithms have inline comments
- [ ] Type hints on all function signatures
- [ ] Examples in docstrings for complex usage

---

## Code Review Checklist

Before marking a task complete, verify:

### Functionality
- [ ] Code works as specified in plan.md
- [ ] Success criteria met
- [ ] Manual testing performed
- [ ] Edge cases handled

### Tests
- [ ] Unit tests written
- [ ] All tests pass
- [ ] Coverage >80% for new code
- [ ] Integration tests (if applicable)

### Documentation
- [ ] Module docstring present
- [ ] All public APIs documented
- [ ] Type hints added
- [ ] Examples provided for complex usage

### Code Quality
- [ ] Follows PEP 8 / Black formatting
- [ ] No code duplication
- [ ] Proper error handling
- [ ] No hardcoded values (use config)
- [ ] Logging added for debugging

### Integration
- [ ] Integrates with existing code
- [ ] Doesn't break existing functionality
- [ ] Messages/events used correctly
- [ ] Plugin interface followed

---

## Git Commit Guidelines

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

**Examples**:
```
feat(core): implement event bus with priority handling

- Add Event base class with timestamp
- Add EventPriority enum
- Implement EventBus with subscribe/publish/unsubscribe
- Add unit tests with 95% coverage

Closes #1
```

```
fix(audio): resolve stereo panning calculation error

The panning calculation was inverted, causing left sounds to play
on the right speaker. Fixed the sign in the pan calculation.

Fixes #15
```

### When to Commit

- After completing each task
- After writing tests
- Before switching to different task
- When reaching a stable state

**Commit often, push less frequently.**

---

## Development Workflow

### Standard Process

1. **Read task** from plan.md
2. **Understand requirements** fully (ask if unclear)
3. **Write tests** (TDD approach) or plan tests
4. **Implement code** with documentation
5. **Run tests** and verify they pass
6. **Manual testing** of functionality
7. **Code review** (self-review checklist)
8. **Update plan.md** to mark task complete
9. **Commit changes** with descriptive message
10. **Move to next task**

### Phase Completion Process

1. **Complete all tasks** in phase
2. **Run full test suite** for the phase
3. **Perform code quality assessment**
4. **Verify success criteria** from plan.md
5. **Write phase completion report**
6. **Update plan.md** with completion status
7. **Commit phase completion**
8. **Ask user** for approval to proceed to next phase

---

## Problem-Solving Approach

When encountering issues:

1. **Reproduce the issue** reliably
2. **Write a failing test** that demonstrates the bug
3. **Debug systematically**:
   - Add logging/print statements
   - Use Python debugger (pdb)
   - Check assumptions
4. **Fix the issue** with minimal changes
5. **Verify the test passes** now
6. **Check for regressions** (run all tests)
7. **Document the fix** (commit message, code comments)

---

## Communication Protocol

### Status Updates

Provide regular updates:
- "Starting Phase X, Task Y"
- "Completed Task Y, moving to Task Z"
- "Phase X complete, running assessment"
- "Blocked on [issue], need guidance"

### Asking for Help

Format questions clearly:
```
**Context**: Working on [task] in Phase X

**Issue**: [Description of problem]

**What I've tried**:
- Approach 1: [result]
- Approach 2: [result]

**Question**: [Specific question]

**Impact**: [Blocking/Non-blocking]
```

### Reporting Progress

End of day summary:
```
**Completed Today**:
- Task 1.1: Event Bus ✅
- Task 1.2: Message Queue ✅

**In Progress**:
- Task 1.3: Plugin Interface 🚧

**Blockers**: None / [Description]

**Tomorrow's Plan**: Complete Task 1.3, start Task 1.4
```

---

## Quality Standards Summary

### Code Must Be:
- ✅ Functional (meets requirements)
- ✅ Tested (>80% coverage)
- ✅ Documented (docstrings + comments)
- ✅ Typed (type hints everywhere)
- ✅ Formatted (Black, PEP 8)
- ✅ Maintainable (clean, clear, modular)

### Never Compromise On:
- ❌ Skipping tests
- ❌ Missing documentation
- ❌ Ignoring errors/warnings
- ❌ Hardcoding values
- ❌ Code duplication
- ❌ Unclear variable names

---

## Final Reminders

1. **Follow plan.md** - It's your roadmap
2. **Update plan.md** - Track your progress
3. **Ask when unsure** - Don't guess
4. **Test everything** - No exceptions
5. **Document thoroughly** - Future developers will thank you
6. **Assess quality** - After every phase
7. **Commit frequently** - Save your work
8. **Communicate clearly** - Keep user informed

---

## Getting Started

Now that you've read this guide:

1. Read `plan.md` from start to finish
2. Start with Phase 0: Project Setup
3. Follow the workflow outlined above
4. Ask questions as needed

**Good luck, and build something amazing!** 🚀
