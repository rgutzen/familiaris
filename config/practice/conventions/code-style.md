# Code style — research software engineering

Always-on constraints for Python research software. These are **dispositions**,
not a procedure — they apply whenever code is written or reviewed, without being
invoked.

## Priority order

**Correctness > Performance > Maintainability > everything else.**
Scientific integrity is never traded for elegance or speed.

## Building blocks, not puzzle pieces

Design flexible, reusable components rather than rigid, tightly-coupled ones.

- Composition over inheritance; narrow focused interfaces over monolithic classes
- Separate data structures from algorithms
- Utilities solve one thing well; no assumptions about how they will be combined
- Provide both high-level convenience functions and low-level blocks
- Document components by **what they do**, not what workflow they belong to
- When one component fails, the system should not completely break

## Solution hierarchy

Always start at the simplest level that could work, and say which level you chose:

| L | Approach |
|---|---|
| 0 | Reorganisation — can restructuring files or data solve it? |
| 1 | Tool-native features — does the tool already support this? |
| 2 | Configuration only |
| 3 | Parameter modification |
| 4 | Compose existing blocks |
| 5 | Extend existing code |
| 6 | New building block |
| 7 | New abstraction — rarely needed |

- **Deletion beats addition.** Ask whether the thing needs to exist before asking how little of it to build.
- **Work with the grain** of existing tools. Prefer native features over
abstractions built on top of them.
- **Use tracer bullets**. Build a tiny, end-to-end slice of features first, seek feedback, then expand out from there.

## Verifiable correctness

- Verify maths against the equations in the paper or docs
- Check dimensional analysis — tensor shapes, physical units, time constants
- Ensure numerical stability; avoid overflow and underflow
- Validate against analytical solutions, simplified cases, published benchmarks
- Consider boundary conditions and edge cases
- Fixed random seeds where determinism is required; document every source of
  randomness and its purpose
- Make assumptions explicit in documentation

## Performance

Profile before optimising. Algorithmic improvements before micro-optimisation.
Vectorise and batch. Minimise CPU–GPU transfer; keep computation on device.
In-place operations where appropriate. Mixed precision when
appropriate. Design for data parallelism across GPUs.

## Documentation

Follow **Diátaxis** — tutorials, how-tos, explanation, reference.

- Module: purpose, main classes/functions, relationships
- Class: responsibility, key methods, usage examples, scientific context
- Function: parameters with scientific meaning and units, returns, exceptions
- Inline: non-obvious choices, scientific rationale, performance considerations

Prefer transparency over abstraction in research contexts.

## Verification

Code review should be able to name which solution-hierarchy level was chosen and
why a lower one was rejected.
