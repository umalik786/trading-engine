# Write-ups

One file per phase, written as that phase clears.

## What these are

`project-alignment.md` §9 makes the case: **"How I test that my backtester isn't lying
to me" is a better artifact than a P&L curve**, it is honest, and it exists in weeks
rather than months. These files are that artifact, one per phase.

Writing each one as its phase clears, rather than in a batch afterwards, is the point.
The reasoning behind a decision is available while it is being made and gone a month
later; a write-up assembled from a finished repository records what the code does, not
why it turned out that way or what was nearly done instead.

## Written by the operator. Claude Code does not draft them

Claude Code writes the engine. It does not write these.

The reason is the same one that keeps the property tests hand-written (spec §7.3): an
account of whether the system can be trusted, produced by the thing being trusted, is
not evidence. A write-up drafted by Claude Code would describe the implementation as
Claude Code understood it — including any point where that understanding was wrong,
stated just as confidently as the parts that were right. The value of these files is
that they are an independent reading.

That reading is also the thing being offered. The 1:1 engineering framing in §9 rests
on the operator being able to explain the system, not on the system existing.

## Publication

Written from phase 0 onward, **published from phase 5 onward** — §9 sets publication at
phase 5, not phase 10, because nothing in the credibility case requires live results.
Phases before that are written up on the same schedule and held.

## Convention

One Markdown file per phase, named for the phase and its subject, e.g.
`phase-3-costs-and-sizing.md`. A phase whose write-up is still outstanding is simply
absent from this directory.
