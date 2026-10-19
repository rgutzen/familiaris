# Trigger Index

<!-- GENERATED FILE — do not hand-edit. Rebuild: `familiar skills index` -->
<!-- READ ON DEMAND. Never injected — it costs zero always-loaded tokens and may grow to any size. -->

Resolution signal 3 ([[skill-routing]]). Match task
vocabulary against the terms below; a match is **explainable** — you can name
the term that fired, which an embedding similarity cannot.

**An antitrigger match suppresses the skill even if a trigger also matched.**
Check §Antitriggers before acting on a trigger hit.

59 triggers and 39 antitriggers over 8 skills.

## Triggers

| Term | Skill | Subject | Trust |
|---|---|---|---|
| add skill | `adopt-skill` | skills | trusted |
| adopt skill | `adopt-skill` | skills | trusted |
| agent persona | `prompt-engineering` | harness | trusted |
| agent should know about me | `personalize-context` | practice | trial |
| api endpoints | `app-builder` | practice | trusted |
| architect mode | `wizard` | practice | trusted |
| assess this paper | `paper-review` | knowledge | trusted |
| build an app | `app-builder` | practice | trusted |
| collaboration.md | `personalize-context` | practice | trial |
| complex feature | `wizard` | practice | trusted |
| compose prompts | `prompt-engineering` | harness | trusted |
| computational model | `research-software-engineering` | practice | trusted |
| consensus | `literature-review` | knowledge | trusted |
| contradictions in the literature | `literature-review` | knowledge | trusted |
| corpus | `literature-review` | knowledge | trusted |
| crud app | `app-builder` | practice | trusted |
| edit user.md | `personalize-context` | practice | trial |
| full stack | `app-builder` | practice | trusted |
| gpu pipeline | `research-software-engineering` | practice | trusted |
| hpc workflow | `research-software-engineering` | practice | trusted |
| import skill | `adopt-skill` | skills | trusted |
| install skill | `adopt-skill` | skills | trusted |
| journal review | `paper-review` | knowledge | trusted |
| literature review | `literature-review` | knowledge | trusted |
| make an agent | `prompt-engineering` | harness | trusted |
| mobile app | `app-builder` | practice | trusted |
| multi-file change | `wizard` | practice | trusted |
| new skill | `adopt-skill` | skills | trusted |
| peer review | `paper-review` | knowledge | trusted |
| personalise user.md | `personalize-context` | practice | trial |
| personalize user.md | `personalize-context` | practice | trial |
| prompt architecture | `prompt-engineering` | harness | trusted |
| quality gate | `wizard` | practice | trusted |
| refactor pipeline | `research-software-engineering` | practice | trusted |
| refactor subsystem | `wizard` | practice | trusted |
| referee report | `paper-review` | knowledge | trusted |
| related work | `literature-review` | knowledge | trusted |
| reproducibility | `research-software-engineering` | practice | trusted |
| research code | `research-software-engineering` | practice | trusted |
| research software | `research-software-engineering` | practice | trusted |
| review this manuscript | `paper-review` | knowledge | trusted |
| reviewer 2 | `paper-review` | knowledge | trusted |
| rse | `research-software-engineering` | practice | trusted |
| scaffold application | `app-builder` | practice | trusted |
| scientific python | `research-software-engineering` | practice | trusted |
| skill from book | `adopt-skill` | skills | trusted |
| skill from repo | `adopt-skill` | skills | trusted |
| synthesise papers | `literature-review` | knowledge | trusted |
| system prompt | `prompt-engineering` | harness | trusted |
| systematic review | `literature-review` | knowledge | trusted |
| systemic bug | `wizard` | practice | trusted |
| tune my context | `personalize-context` | practice | trial |
| vendor skill | `adopt-skill` | skills | trusted |
| voice.md | `personalize-context` | practice | trial |
| web app | `app-builder` | practice | trusted |
| who am i file | `personalize-context` | practice | trial |
| wizard | `wizard` | practice | trusted |
| write a prompt | `prompt-engineering` | harness | trusted |
| write my conventions | `personalize-context` | practice | trial |

## Antitriggers

| Term | Suppresses |
|---|---|
| adopt a skill | `personalize-context`, `prompt-engineering` |
| analysis pipeline | `app-builder` |
| author a skill | `adopt-skill` |
| code review | `paper-review` |
| corpus synthesis | `paper-review` |
| debug a failure | `research-software-engineering` |
| debug a prompt failure | `prompt-engineering` |
| find papers | `literature-review` |
| install a skill | `prompt-engineering` |
| journal entry | `personalize-context` |
| knowledge leaf | `personalize-context` |
| literature review | `paper-review` |
| notebook | `app-builder` |
| one-liner | `wizard` |
| one-off | `research-software-engineering` |
| peer review | `literature-review` |
| prompt engineering | `personalize-context` |
| prototype | `research-software-engineering` |
| quick fix | `wizard` |
| quick script | `research-software-engineering` |
| read the code | `wizard` |
| refactor existing | `app-builder` |
| research code | `app-builder` |
| review one manuscript | `literature-review` |
| run a skill | `adopt-skill` |
| script | `app-builder` |
| skill-creator | `adopt-skill` |
| spike | `research-software-engineering`, `wizard` |
| throwaway | `research-software-engineering`, `wizard` |
| use a skill | `adopt-skill`, `prompt-engineering` |
| write a paper | `literature-review` |
| write a skill | `personalize-context` |
| write a skill body | `adopt-skill` |
| write a test | `research-software-engineering` |
| write my paper | `paper-review` |

## Ambiguous terms

None — every trigger term selects exactly one skill.

A term that selects more than one skill cannot resolve at signal 3 alone;
fall through to a subject browse, or tighten the trigger vocabulary.
