# Extended Clip

[[README|К карте спецификации]] · Статус документа: **TARGET**

## Пользовательский сценарий

Пользователь замечает событие, нажимает Extended Clip Start, продолжает играть/записывать и позже нажимает Finish. SayClip сохраняет прошлое из Replay Buffer, добавляет последующую Recording и передаёт единый файл в голосовое именование.

## Предусловия Start

Start **MUST** приниматься только если:

- Bridge подключён и OBS state свежий;
- Replay Buffer активен;
- Recording не активна;
- нет другой `ExtendedClipSession`;
- нет конфликтующей обычной операции.

При отказе OBS state **MUST NOT** изменяться.

## Успешный Start flow

1. Backend атомарно создаёт единственную `ExtendedClipSession`.
2. Bridge запускает OBS Recording.
3. Только после подтверждённого `RECORDING_STARTED` Bridge ждёт configurable overlap delay.
4. Bridge вызывает Save Replay Buffer.
5. После `REPLAY_BUFFER_SAVED` session сохраняет точный replay path.
6. Session входит в `capturing`; Replay Buffer остаётся активным.

Значение overlap delay настраивается; fallback для keyframe interval разрешён. Это не consumer contract.

## Finish flow

Finish становится доступен только после подтверждённого replay path и перехода session в `capturing`. Во время `starting_recording`, `waiting_overlap` и `saving_replay` он отклоняется как `operation_busy`; запрос не ставится в очередь.

1. Backend принимает Finish только для активной session и фиксирует commit.
2. После commit Cancel **MUST** быть отключён.
3. Bridge останавливает только Recording, принадлежащую session.
4. `RECORDING_STOPPED` сообщает точный recording path.
5. Backend проверяет совместимость, находит overlap, выполняет merge и validation.
6. Успешный output создаёт один `extended_clip` naming job.
7. После voice naming session завершается.

## Cancel flow

Cancel до Finish commit:

- **MUST** остановить только Recording, созданную этой session;
- **MUST NOT** останавливать Replay Buffer;
- **MUST NOT** запускать merge или naming;
- **MUST NOT** удалять replay, recording или diagnostics;
- завершает session после подтверждения остановки Recording.

Если пользователь вручную остановил Recording в OBS до Finish, это **MUST** считаться Cancel, а не Finish. Merge не запускается.

## Внутренний автомат

`ExtendedClipPhase` — backend-only implementation detail:

| Phase | Что происходит | Публичная проекция |
|---|---|---|
| `idle` | session отсутствует | `ready`, stage `idle` |
| `starting_recording` | команда старта отправлена, ждём OBS event | `recording` |
| `waiting_overlap` | Recording работает, ждём overlap delay | `recording` |
| `saving_replay` | сохраняется replay snapshot этой session | `recording` |
| `capturing` | replay path известен, Recording продолжается | `recording` |
| `stopping_recording` | Finish принят, ждём recording path | `processing` |
| `matching` | ищется точный overlap | `processing` |
| `merging` | создаётся объединённый файл | `processing` |
| `validating` | проверяются streams, timestamps и seam | `processing` |
| `naming` | voice naming готового output | `listening` или `processing` |
| `cancelled` | session отменена без merge | краткий `done` или `ready` |
| `done` | output готов | `done` |
| `error` | безопасный отказ, sources сохранены | `error` |

Backend может менять или дробить внутренние фазы без изменения consumer contract.

## Повторные нажатия

В MVP специальный debounce и `finish_requested` **MUST NOT** реализовываться. Атомарная проверка session остаётся обязательной:

- повторный Start после принятого Start отклоняется как `extended_clip_active`;
- повторный Finish после commit отклоняется как `processing_committed`;
- Finish до `capturing` отклоняется как `operation_busy`;
- Cancel после commit отклоняется как `processing_committed`.

## Конкурентный Save Clip

- Пока Extended Clip создаёт собственный replay snapshot, Save Clip отключён во избежание смешивания OBS replay events.
- В `capturing` обычный Save Clip разрешён.
- Пока обычный Save Clip проходит command/naming pipeline, Extended Recording продолжает работать.
- Finish в этот момент не ставится в очередь и отклоняется с `operation_busy`; пользователь может повторить его после освобождения pipeline.
- Cancel остаётся доступным до Finish commit.

## Владение Recording

Session **MUST** хранить признак подтверждённого старта и идентичность ожидаемого output настолько строго, насколько позволяет OBS API. Ни Cancel, ни failure cleanup **MUST NOT** останавливать Recording, которая существовала до session или была запущена независимо.
