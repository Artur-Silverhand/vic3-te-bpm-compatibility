# Допустимая латиница TE

Точные исключения: `translations/data/latin_allowlist.json`. Каждая запись привязана к ключу и SHA-256 полного значения, поэтому не разрешает произвольный будущий английский текст.

## Названия компаний и брендов

Следующие 34 собственных названия сохранены в исходной латинской форме. Названия вымышленных компаний также рассматриваются как названия, заданные модом.

| Ключ | Название |
| --- | --- |
| `company_airbus` | Airbus |
| `company_alibaba` | Alibaba |
| `company_amazon` | Amazon |
| `company_apple` | Apple |
| `company_blackberry` | BlackBerry |
| `company_bp` | BP |
| `company_bytedance` | ByteDance |
| `company_dassault_aviation` | Dassault Aviation |
| `company_google` | Google |
| `company_hp` | Hewlett-Packard |
| `company_huawei` | Huawei |
| `company_hyundai` | Hyundai |
| `company_intel` | Intel |
| `company_jsw_steel` | JSW Steel |
| `company_lockheed_martin` | Lockheed Martin |
| `company_microsoft` | Microsoft |
| `company_netflix` | Netflix |
| `company_nintendo` | Nintendo |
| `company_nvidia` | Nvidia |
| `company_openai` | OpenAI |
| `company_pfizer` | Pfizer |
| `company_rekal` | Rekal Incorporated |
| `company_reliance` | Reliance Industries |
| `company_samsung` | Samsung |
| `company_saudi_aramco` | Saudi Aramco |
| `company_shell` | Royal Dutch Shell |
| `company_softbank` | SoftBank |
| `company_sony` | Sony |
| `company_spacex` | SpaceX |
| `company_toyota` | Toyota |
| `company_tsmc` | TSMC |
| `company_tycho_manufacturing` | Tycho Manufacturing & Engineering |
| `company_verizon` | Verizon |
| `company_volkswagen` | Volkswagen |

## Остальные точные исключения

- `te_systems_window_launcher_label`, `te_systems_window_title`: собственное название мода `Timeline Extended`.
- `te_law_tax_delta_effects`, `te_law_tax_effects`, `te_law_tax_effects_country`: имена целей подсказок внутри директив `#tooltip`; это служебные идентификаторы, а не английские подписи.
- `je_space_race_widget_modules_col_b`: римская цифра `II`, обозначающая столбец модулей.

## Латиница внутри русского текста

Она не требует исключений для целиком латинских строк, но сохранена осознанно:

- `XIV` в имени Людовика XIV и обозначении XIV века — римская запись числа.
- `window_gate` — имя отладочной проверки.
- `docs/testing/solar-colonies-playtest.md` и `debug.log` — пути и имена файлов.
- `Shift`, `Ctrl`, `Alt`, `JADC2` — обозначения клавиш и системы командования.
- `_add`, `_mult`, `TE_DEMOG_RATES`, `mb`, `md`, `applied_b` и подобные имена — параметры модификаторов и диагностические поля; в отладочных описаниях они должны совпадать с кодом.

Проверенные английские фразы, заголовки и статусы переведены в `translations/data/te_qa_overrides.json`. Исключения не используются для сокрытия непереведённых предложений.
