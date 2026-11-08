# TE core systems: Russian review

Source: `sources/upstream/Vic3TimelineExtended/localization/english`, pinned upstream `48a28e73`.
Output: `translations/data/te_systems_overrides.json`.

All **2,018 keys** in the assigned 11 files are covered:

| File stem | Keys |
| --- | ---: |
| te_budget | 152 |
| te_diplomacy | 148 |
| te_power_blocs | 63 |
| te_power_bloc_unlocks | 88 |
| te_tax | 818 |
| te_tax_generated | 430 |
| te_nation_generated | 166 |
| te_un_button_effects | 1 |
| te_mobilization_options | 54 |
| te_combat_units | 60 |
| te_ship_types | 38 |

Russian prose translated and reviewed throughout; repetitive generated text expanded from reviewed Russian templates. Reference-only nation strings and numeric/reference-only strings retain their original expressions. No machine-translation service or paid API was used for this override file.

Terminology follows `translations/data/ru_terms.json` and task vocabulary. Tax-system distinctions are retained: enacted code, draft, bill revision, passage, commencement, temporary expiry, baseline acceptance, commitments, promises and trust. "Light Tax Code" is translated as «Упрощённый налоговый кодекс»; "Rural Assessment" as «Сельский сбор»; "Head Tax" as «Подушный налог».

Validation: 2,018 source keys and 2,018 overrides; zero missing/extra keys, zero mismatched references/script calls/icons/formatting tokens, zero changed literal `\n` counts. Concept display labels are translated while identifiers remain unchanged. No remaining English prose or English Concept display labels (Shift/JADC2, Roman numerals and the version prefix are intentional).

Validation details and reproducible scratch helpers: `runtime/translations/systems_audit.json`, `runtime/translations/systems_audit.py`. Some script-token positions change to allow natural Russian word order; token multisets are preserved. No game/UI launch or installed-mod mutation was performed. In-game layout and dynamic grammatical inflection remain unverified.

Blockers: none.

## Short miscellaneous UI pass

Output: `translations/data/te_ui_overrides.json`, **3,545 reviewed entries**. It contains **1,743 `te_` entries** and **1,802 previously reviewed non-`te_` entries**. The latter were kept stable after the task was repartitioned; remaining non-`te_` keys belong to the other UI reviewer.

The canonical parser exposes 10,342 entries from `te_miscellaneous_l_english.yml`. The agreed short-UI rule is at most 12 `[A-Za-z]+` words in `loclib.plain(value)`, after protected scripts/macros/icons/formatting/escapes are removed. This selects 7,743 keys overall and **1,724 `te_` keys**. All 1,724 are covered; the file also retains 19 earlier reviewed `te_` entries outside that stricter cutoff. Initial preliminary counts used a simpler row parser and hyphenated-word counting; canonical counts above supersede them.

Coverage includes all selected demography and strategic-reserve entries, monument-skin and landmark names, reviewed basic labels, plus the complete short `te_` UI slice: power grids, maps, national figures, monetary policy, bloc slots/summits, orbit/debris, seabed administration and licenses, judiciary, trade and window controls. Repetitive strings were expanded from individually reviewed templates. Concept display labels were also translated. Exact-match seeds were semantically checked and misleading name-based translations were corrected. Offline machine drafts were not automatically promoted into this reviewed file.

Final QA with the repository's canonical `loclib.validate`: **zero errors in 3,545 UI entries**, **zero missing short `te_` keys**, and **zero errors in the accepted 2,018 systems entries**. Canonical source coverage of the original eleven system files remains 2,018/2,018. Audit: `runtime/translations/ui_audit.json`.

No source structural defects were identified in the reviewed scope. Named `#tooltip:` targets, `#indent_newline:3`, escaped rank markers, script expressions and other protected syntax retain their upstream behavior. Intentional Latin text includes the mod's brand `Timeline Extended`, debug identifier `window_gate`, Roman numerals, Shift and JADC2. No game/UI launch was performed; text fit and dynamic grammatical inflection remain unverified.

Blockers in this agent's assigned scope: none.

## Final Latin/structural and numeric QA

Additional reviewed corrections: `translations/data/te_qa_overrides.json`, **166 entries**. The first 148 repair untranslated Latin-only content and structural failures (including lost formatting whitespace and truncated UN descriptions); 18 more are complete translations restoring missing/altered numeric conditions in debug, demography, tourism, UN, construction and nuclear UI text. Current `loclib.validate` and `numeric_profile` pass for all 18 numeric corrections; all 166 pass structural validation. No overlap with other current override files was introduced.

Exact Latin exceptions: `translations/data/latin_allowlist.json`, **40 TE entries**, covering 34 company names, two mod-brand labels, three internal tooltip-target strings and Roman column number II. Each exception stores the SHA-256 of the whole output value and a specific reason. The separate explanation is `translations/docs/te-latin-exceptions.md`. Mixed Russian text deliberately retains Roman XIV, keyboard names and code/debug identifiers; these are not untranslated English prose.

Numeric review was normalized from 228 preliminary candidates to 34 actual review candidates. This agent and the core reviewer supplied **18 full corrections** and **5 exact numeric exceptions** in `translations/data/te_numeric_allowlist.json` (5 written as a Russian word, 3D as «трёхмерная», 20th as XX). Each exception binds both the English and Russian full-value hashes and gives the linguistic reason. Main owns the remaining 11 full translations in `te_long_qa_overrides.json`; they were not edited or merged here. Thus the 34-candidate division is 18 corrections + 5 justified exceptions + 11 main corrections.

The proposed Latin exceptions and current human overrides leave no unresolved Latin-only TE text in the latest inspected output. A subsequent main rebuild is responsible for the final complete-pack totals and packaging.
