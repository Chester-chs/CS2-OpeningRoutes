# CS2 OpeningRoutes

**English** | [简体中文](README.zh-CN.md)

**Learn how a professional player or team plays a specific area in CS2.**

OpeningRoutes turns professional match demos into **player/team → map → side → area or role** profiles. Study opening movement and utility timing, compare situations, open the full round, and save a practice checklist.

> **v0.2.0 local development preview.** The Windows application and functional web edition share player-area profiles, independent pistol-round study, full-round playback and local practice records. The desktop studio also creates plan drafts and exports reviewed static content. Observed match behavior is distinguished from instruction verified through in-game reproduction.

## Player and area profiles

- Common positions, movement sequences and utility timing in the first 30 seconds, with the full round retained.
- Pistol, economy and score contexts, each with unique round/match counts and uncertainty indicators.
- Alive presence by area, first damage and kill, opposing utility, and round outcomes. Counterplay and tactical intent require human review.
- SteamID identity, name history, separate team periods and game versions. Manually confirmed role groups retain individual profiles.

Select a real sample to view all ten players' routes or save a checklist with actual movement and throw times. Progress and notes stay in the current browser and can be backed up. Desktop users can create a plan draft from the same round; publication still requires the existing verified teaching evidence. Rounds without utility remain useful for movement practice.

## Pistol rounds and supporting material

Pistol rounds retain a dedicated entry for equipment, routes, opening kills, plants and outcomes, with links into player-area learning. Existing CT research, utility records, match footage and verified reproduction lessons support that workflow. Further lineup grouping and throw-video production are outside the current development focus.

## Evidence and limits

Profiles include only source-verified, complete formal rounds without unresolved review flags. Routes are sampled at 4 Hz; throw events retain precise timing separately. Two seconds of uncontested alive presence is an occupancy proxy, not proof of tactical control. First damage is a contact proxy, not visibility.

Profiles below 30 rounds or five matches are exploratory. At least five matches are required for 95% match-block bootstrap intervals. Frequencies and outcomes are descriptive, not evidence of the best play or a causal advantage. Missing data and game-version differences are shown explicitly.

## Run and learn more

See the [usage guide (Chinese)](docs/usage.zh-CN.md) for source setup, local browser mode, Windows packaging and static export. The web edition reads reviewed content and stores practice records in the browser; importing and curation remain in the desktop studio.

- [Project scope and roadmap (Chinese)](docs/project-plan.zh-CN.md)
- [Player-area learning specification (Chinese)](docs/plans/player-area-learning.zh-CN.md)
- [CT research methods and attribution (Chinese)](docs/ct-research.zh-CN.md)
