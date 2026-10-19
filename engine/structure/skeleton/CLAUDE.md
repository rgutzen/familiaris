<!-- Seeded by `familiar structure skeleton` from engine/structure/skeleton/.
     Yours from here on. Point, do not copy: every fact lives in one file. -->

# CLAUDE.md

Guidance for Claude Code in this repository.

| You need | Read |
|---|---|
| how agents work here, and where knowledge lives | **`CONTEXT.md`** — start there |
| how to use the system, what runs | `README.md` |
| what the tree is made of | `STRUCTURE.md` |
| where bytes live, and the storage rules | `STORAGE-MODEL.md` |
| what agents must not touch | `config/boundaries/CONTEXT.md` |

- **Run the gate before a commit:** `python3 engine/checks/checks.py --run pre-commit`.
- **Generated files are never hand-edited** — `STRUCTURE.md`'s marked blocks,
  `memory/knowledge/INDEX.md`, the skill routers. Edit the source and rerun.
- **Boundaries are enforced by the compiled guards, not by this file.** Change
  them in `config/boundaries/*.yaml` and run `engine/boundaries/compile.py`.
