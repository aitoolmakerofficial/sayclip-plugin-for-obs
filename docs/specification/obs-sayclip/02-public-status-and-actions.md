# Публичные статусы и действия

[[README|К карте спецификации]] · Статус документа: **TARGET**

## Главное правило

Внутренний workflow может быть подробным, но consumer **MUST NOT** знать, ищется ли overlap, выполняется merge или validation. Backend **MUST** вернуть один стабильный `ui_state` и полную карту `actions`.

## Public UI state

| `ui_state` | Что видит пользователь | Смысл |
|---|---|---|
| `offline` | Offline | backend или Bridge недоступен |
| `ready` | Ready | система готова принять действие |
| `recording` | Recording — do not stop OBS | Extended Clip сейчас записывает продолжение |
| `processing` | Processing — please wait | запись остановлена; файл собирается/проверяется/именуется |
| `listening` | Speak | идёт захват голосового имени |
| `done` | Done | операция завершилась |
| `error` | Error + безопасное сообщение | операция завершилась ошибкой |

Текст может отличаться между Dock и Stream Deck, но смысл состояния **MUST** сохраняться. Подробная `ExtendedClipPhase` не является consumer contract.

## Extended Clip projection

Backend **SHOULD** возвращать стабильную проекцию:

```json
{
  "extended_clip": {
    "active": true,
    "stage": "recording"
  }
}
```

`stage` имеет только `idle`, `recording`, `processing`. Это не внутренний автомат. Поле `active` истинно для `recording` и `processing`.

## Action availability

Каждый consumer **MUST** строить кнопки только по `actions`, полученному от backend:

```json
{
  "actions": {
    "save_moment": {"enabled": true, "reason": null},
    "save_recording": {"enabled": false, "reason": "extended_clip_active"},
    "extended_clip_start": {"enabled": false, "reason": "extended_clip_active"},
    "extended_clip_finish": {"enabled": true, "reason": null},
    "extended_clip_cancel": {"enabled": true, "reason": null}
  }
}
```

`reason` — машинный код, не пользовательский текст и не глобальный статус. UI **SHOULD** преобразовать его в tooltip для disabled action или toast для отклонённого запроса. Неизвестный reason **MUST** иметь нейтральный fallback «Action is unavailable».

Минимальный vocabulary причин:

- `bridge_disconnected`
- `obs_state_stale`
- `replay_buffer_inactive`
- `recording_inactive`
- `recording_already_active`
- `extended_clip_inactive`
- `extended_clip_active`
- `operation_busy`
- `processing_committed`

## Матрица действий

| Ситуация | Save Clip | Save Recording | Extended Start | Extended Finish | Extended Cancel |
|---|---:|---:|---:|---:|---:|
| Idle, Replay ON, Recording OFF | on | off | on | off | off |
| Idle, обычная Recording ON | зависит от Replay | on | off | off | off |
| Extended Clip запускает Recording/сохраняет свой Replay | off | off | off | off (`operation_busy`) | on |
| Extended Clip записывает (`capturing`) | on | off | off | on | on |
| Обычный Save Clip naming во время `capturing` | off как busy | off | off | off (`operation_busy`) | on |
| Finish принят; stop/merge/validation/naming | off | off | off | off | off |
| Bridge/OBS state неизвестен | off | off | off | off | off |

Обычный Save Clip разрешён во время устойчивого `capturing`, потому что Replay Buffer продолжает работать. Очереди обычных операций в MVP **MUST NOT** добавляться.

## Приоритет единого статуса

Для одной глобальной status panel backend **SHOULD** вычислять presentation state в таком порядке:

1. offline;
2. error;
3. listening;
4. Extended Clip processing;
5. Extended Clip recording;
6. обычная operation processing;
7. done;
8. ready.

## Dock и Stream Deck

- Dock **MUST** сохранить одну общую status panel.
- В текущую версию Dock добавляется одна контекстная кнопка Extended Clip. Она показывает Start или Finish по `actions`/`extended_clip.stage`.
- Отдельная DOM-кнопка Cancel в Dock **DEFERRED**; endpoint и action contract всё равно обязательны.
- Stream Deck plugin будет согласован позднее и **MUST** использовать тот же `/api/status`, не собственные таймеры или предположения.
- Клиент **MUST NOT** оптимистично переключать Start → Finish до ответа backend и следующего status snapshot.
- Пока Start ещё ждёт `RECORDING_STARTED` или `REPLAY_BUFFER_SAVED`, Finish отключён. Очереди и `finish_requested` в MVP отсутствуют.
