# 0.6.0-dev — experimental compatibility candidate

Victoria 3 1.15.0; Timeline Extended 48a28e73 + full BPM d785d399.

- Integrated common laws, political stances, parties, characters, production,
  institutions, tax reforms and overlapping UI definitions.
- Resolved duplicate event/value definitions and competing law-checkpoint effects.
- Bounded cabinet candidate selection to 16 attempts, stop on no insertion;
  clear scratch lists and discard duplicate/dead/foreign references.
- Calculate cabinet consensus with one min/max scan per active law, preserving
  the original stance function and all-law denominator.
- Synthetic gate: 61 tests passed, including 400 formula comparisons and 5000
  candidate turnover cycles. Static reference/call-graph gate passed.

Load order: Timeline Extended → full Better Politics Mod → this patch.
Install both parent mods separately; disable duplicate Workshop/local copies.
New single-player campaigns only. No claim of multiplayer or old-save support.

Engine loading, UI, save/reload, long-campaign balance and actual performance are
not yet accepted. No game was launched for this release's synthetic checks.
Workshop TE differed from the pinned GitHub source in 12 checked files; current
Workshop updates are not automatically covered by the pinned-source PASS.

Archive SHA256:
`4e816b169b6579830848b52eb4b19c099cb93a0953436bdbd4a9f8c68a85b537`.

