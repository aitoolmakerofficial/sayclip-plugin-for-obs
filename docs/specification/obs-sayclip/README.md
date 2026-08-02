# OBS SayClip specification

Текущая major-версия контракта: **SayClip 2.0.0**. Версия 2 вводит новый публичный `ui_state`, расширенную карту `actions` и Extended Clip API.

Эта папка — каноническая спецификация домена OBS SayClip. Документы связаны Obsidian-ссылками и разделяют фактическое поведение текущего кода, целевое поведение и отложенные решения.

> [!important]
> Нормативные слова **MUST**, **MUST NOT**, **SHOULD** и **SHOULD NOT** описывают обязательность целевого поведения. Метки **CURRENT**, **TARGET** и **DEFERRED** показывают статус реализации.

## Карта знаний

- [[00-domain-ontology|Доменная онтология]] — единая точка входа, сущности и границы ответственности.
- [[01-current-system|Текущая система]] — поведение, которое уже существует в коде.
- [[02-public-status-and-actions|Публичные статусы и действия]] — стабильный контракт для Dock и Stream Deck.
- [[03-extended-clip|Extended Clip]] — пользовательский сценарий, внутренний автомат и orchestration OBS.
- [[04-api-contract|HTTP и Bridge API]] — endpoints, ответы и команды Bridge.
- [[05-media-merge|Media merge]] — overlap, stream copy, MKV и MP4.
- [[06-failures-and-file-safety|Сбои и сохранность файлов]] — отмена, остановка компонентов и правило удаления.
- [[07-decisions|Реестр решений]] — принятые и отложенные решения.
- [[08-stream-deck-plugin-tz|ТЗ Stream Deck plugin]] — внешний consumer, actions, состояния и acceptance criteria.
- [[09-obs-bridge-plugin-tz|ТЗ OBS Bridge plugin]] — команды OBS, events, ownership и точное разделение status-протоколов.

## Иерархия источников истины

1. Эта папка — целевая спецификация.
2. Автотесты и код — источник истины для **CURRENT**.
3. `SayClip_Replay_Sequence_Architecture.md` — исследовательская заметка. Она может содержать устаревшие названия и решения и **MUST NOT** использоваться как контракт без сверки с этой спецификацией.
4. `replay_overlap_probe.py` — ручная CLI-обёртка над production-модулем `use_cases/extended_clip/overlap.py`; сам backend **MUST NOT** зависеть от наличия этого корневого файла.

## Термины

Пользовательское название функции — **Extended Clip**. В коде новые сущности **SHOULD** называться `ExtendedClipSession`, `ExtendedClipPhase` и `ExtendedClipService`. Названия `SequenceSession`, `sequence merge` и `replay sequence` считаются историческими.
