# CS2 OpeningRoutes

**English** | [简体中文](README.zh-CN.md)

Study professional Counter-Strike 2 players' opening routes: how CTs establish their defense and how Ts spread out during early defaults.

> **Status: concept saved; development deferred.** This repository currently contains planning documents only. Finish [POVForge](https://github.com/Chester-chs/CS2-povforge) first; resume this project when explicitly requested. No application, installer, or working demo is available yet.

## The idea

Watching several rounds individually makes it hard to remember where a player went, when they arrived, and how their opening changed between rounds. OpeningRoutes is planned as a small, local study tool that places selected rounds side by side on a radar map and a shared relative timeline.

**Planned study flow:**

Import a local demo → select a professional player and rounds → compare opening routes and timings → record observations → save the learning case.

## Planned features

- **CT openings and early T defaults:** study both use cases, comparing rounds from the same side.
- **Route comparison:** show up to three selected rounds on a radar image using distinct colors.
- **Timing markers:** align rounds to freeze-time end and show positions at selected elapsed times.
- **Context alongside the route:** keep spawn position, starting equipment, match, player, and round references visible when available.
- **Learning notes:** keep recorded events separate from the user's tactical interpretation and next-practice goal.
- **Local learning cases:** save a comparison and its notes for later review.

## First-version boundaries

Start with one user-selected map, one selected player, two or three manually selected rounds from the same side, and the first 30 seconds after freeze time ends. The map remains undecided.

Use a static radar with route overlays and simple time controls. Full-match replay, automatic role or tactic classification, cloud accounts, and automatic tactical coaching are outside the first version. Later T-default activity outside the opening window is also outside that initial scope.

Demo positions and events can show what happened. Explanations of intent and judgments about the best play remain user annotations. Missing data must be shown explicitly.

## Technical direction — proposed

Python with [demoparser2](https://github.com/LaihoE/demoparser), a plotting library, and a small local interface. Final interface and storage choices are deferred. Demo-source compatibility, map-coordinate alignment, and timing accuracy must be checked against real samples before development expands.

POVForge can provide optional POV video material for study. An integration has not been designed or implemented.

## Planning

Read the [Chinese project plan](docs/project-plan.zh-CN.md) for the intended workflow, data boundaries, validation criteria, and resumption checklist.

Existing tools already provide replay, notes, and multi-round analysis. This concept focuses on a small, understandable personal learning workflow; uniqueness and learning benefits have not been validated.
