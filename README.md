# CS2 OpeningRoutes

**English** | [简体中文](README.zh-CN.md)

A planned learning library for **T/CT opening map control, utility counters, and professional-player demonstrations**, built from professional-event demos and backed by a searchable, comprehensive utility catalog.

> **Status: direction updated; development deferred.** The 2026-10-27 update changes the READMEs and project plan only; no application code is being written. There is no application, installer, parsing experiment, or working demo yet. Continue improving [POVForge](https://github.com/Chester-chs/CS2-povforge) first and resume implementation only when explicitly requested.

## The idea

Learning to defend a position or contest an area early in the round involves equipment, throwing positions, timing, entry and support roles, responses to opposing utility, and movement after the throw.

OpeningRoutes will organize professional examples by map area and side, connecting individual throws, utility sequences, team coordination, full-round context, and practice instructions. It covers CT opening defense and re-clears as well as T opening control and responses to CT utility.

**Planned learning flow:**

Map → target area → T/CT → proactive control or a response → utility and coordination plan → professional demonstrations and instructional recreations → save for practice.

**Planned content workflow:**

Import professional-event demos and sources → extract utility and full-round context → group throw variants and plans → manually verify purpose and execution → produce demonstrations and instructions → publish to the local learning library.

## Planned core capabilities

- **T/CT opening control and counters:** organize T contests, CT denial or delay, T responses to defensive utility, and CT re-clears around the same area. Explain conditions and opposing actions without promising that a fixed plan always works.
- **Comprehensive utility catalog:** organize available smoke, flash, incendiary/molotov, HE, and other throw records from imported matches. Search by map, area, side, purpose, type, player, and team. Area-based lessons and individual-throw lookup use the same content.
- **Throw variants and coordinated plans:** organize a shared purpose into distinct throw methods with professional examples. Separately record solo or team combinations, order, intervals, and responsibilities. A shared landing point does not automatically mean an identical throw.
- **Professional-player demonstrations:** compare real examples from different players and teams, retaining movement before release, the throw, utility effects, and subsequent positioning, with match and round references.
- **Practice-ready instructions:** show standing and aiming references, throwing technique, timing, movement, and common mistakes. Clearly distinguish original professional-match footage from instructional recreations and label map/game versions and verification status.
- **Conditions and coordination:** retain spawn position, equipment, player count, teammate requirements, and observable opponent actions. Distinguish solo routines from coordinated ones.
- **Full context and cross-match comparisons:** support all available players, formal rounds, and full-round timelines in imported matches. Retain individual/team routes, selected T-default segments, and pistol-round studies.
- **Evidence and learning notes:** show sample counts, date ranges, and successful and unsuccessful examples. Keep observations, tactical interpretations, and practice goals separate.

## Example and coverage boundaries

An area page such as “Ancient → 黑屋 (community callout; exact area to be confirmed)” could organize T opening contests, CT delay or denial, T responses, CT re-clears, and professional throw variants within each plan. This is an information-architecture example, not a verified tactical recipe. Equipment, throw order, and counter instructions require match review and reproduction before becoming teaching content.

“Comprehensive” means systematic organization of imported data with expanding coverage, not a claim to include every possible lineup on every map. Show covered maps, matches, periods, missing fields, and unverified entries.

Professional statistics use verifiable professional-event demos only; a professional player's ranked matchmaking demo does not qualify. Instructional recreations are labeled separately and excluded from professional usage counts.

The product is not limited to one player, two or three rounds, or the first 30 seconds. Openings are the main learning entry point, while later re-clears and context remain accessible. Maps and content can be delivered in stages; validation sample sizes are not product limits.

## Proposed technical direction

Python, [demoparser2](https://github.com/LaihoE/demoparser), map visualization, and a local interface are proposed. Frameworks, storage, and performance targets remain undecided until development resumes.

First validate utility and full-round data from professional demos, then build throw grouping, catalog search, professional demonstrations, area-based control/counter plans, instructions, and saved learning cases. Execution, utility effects, area purpose, and counter interpretations require review. Missing data must remain explicit. Usage frequency or round win rate does not establish the best throw or a causal counter.

POVForge may later help produce player/round clips, but an integration has not been designed or implemented.

## Planning and references

See the [Chinese project plan](docs/project-plan.zh-CN.md) for scope, content structure, staged delivery, and acceptance criteria.

[nades.ai](https://nades.ai/about) and its [utility combinations](https://nades.ai/combos), [CS2.CAM](https://cs2.cam/), and [CS Demo Manager](https://cs-demo-manager.com/docs/guides/2d-viewer) are references. Existing tools already cover overlapping capabilities. This project focuses on a Chinese-language personal learning workflow for area control and counters; differentiation and learning benefits remain unvalidated.
