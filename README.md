# CS2 OpeningRoutes

**English** | [简体中文](README.zh-CN.md)

Study professional Counter-Strike 2 matches through CT defensive openings, team-wide T-default routes, and player/team pistol-round tendencies.

> **Status: concept saved; development deferred.** This repository currently contains planning documents only. Finish [POVForge](https://github.com/Chester-chs/CS2-povforge) first; resume this project when explicitly requested. No application, installer, or working demo is available yet.

## The idea

Watching professional matches individually makes it hard to compare CT defensive setups, the whole T team's default routes, and player/team pistol-round tendencies across matches. OpeningRoutes is planned as a local analysis and learning tool connecting routes, timing, match context, statistics, and review notes.

**Planned study flow:**

Import professional-event demos and record their match sources → select maps, teams, players, and rounds → study routes or pistol-round tendencies → inspect supporting rounds → save the learning case.

## Planned features

- **Professional-event demos only:** organize actual tournament and league matches. A professional player's ranked matchmaking demo does not qualify.
- **CT defensive openings:** compare individual players and team setups, including opening positions, routes, timing, and subsequent movement.
- **Team-wide T-default routes:** study the whole team's movement over the round and inspect user-selected default segments without a fixed 30-second cutoff.
- **Multiple players and rounds:** support all available players and formal rounds in imported matches, including cross-match comparisons. Display grouping must not become a data limit.
- **Player and team pistol-round profiles:** summarize T- and CT-side pistol rounds across matches, covering equipment, setups/routes, timing, utility, opening kills/deaths, and outcomes when supported by the data.
- **Context alongside the route:** retain event, date, teams, lineup, map version, spawn position, equipment, player, and round references when available.
- **Evidence behind summaries:** show sample counts, time ranges, and supporting rounds, including unsuccessful rounds.
- **Learning notes:** keep recorded events separate from the user's tactical interpretation and next-practice goal.
- **Local learning cases:** save a comparison and its notes for later review.

## Confirmed scope and development approach

The product is not restricted to one player, two or three rounds, or the first 30 seconds. Full-round position data is part of the foundation for studying T defaults. CT openings, T defaults, and pistol-round style are three related study modules; the first two also apply to non-pistol rounds.

Keep development approachable through staged delivery: professional-match provenance and full-roster/full-round data, route views and comparisons, then pistol-round summaries. The initial supported map set and interface remain undecided. A small engineering validation sample does not define product limits.

Recorded positions and events support observations; tactical intent, default boundaries, and role labels need user review. Missing data must be explicit. A tendency from a small sample must not be presented as a universal style or a guarantee of success.

## Technical direction — proposed

Python with [demoparser2](https://github.com/LaihoE/demoparser), plotting, and a local interface are proposed. Interface and storage choices are deferred. Demo compatibility, provenance, map coordinates, timing, and formal pistol-round identification must be checked against real samples before results are trusted.

POVForge can provide optional POV video material for study. An integration has not been designed or implemented.

## Planning

Read the [Chinese project plan](docs/project-plan.zh-CN.md) for the intended workflow, data boundaries, validation criteria, and resumption checklist.

Existing tools already provide replay, notes, and multi-round analysis. This concept focuses on a traceable personal analysis and learning workflow; uniqueness and learning benefits have not been validated.
