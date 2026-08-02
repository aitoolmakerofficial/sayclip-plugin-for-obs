# HTTP и Bridge API

Версия контракта: **SayClip 2.0.0**. Изменения consumer API относительно SayClip 1 считаются breaking; Dock и Stream Deck должны использовать общий v2 status contract.

[[README|К карте спецификации]] · Статус документа: **CURRENT + TARGET**

## Consumer endpoints

| Endpoint | Статус | Назначение |
|---|---|---|
| `GET /api/status` | CURRENT, расширяется | каноническое состояние и `actions` |
| `POST /api/save/moment` | CURRENT | сохранить Replay Buffer и назвать файл |
| `POST /api/save/recording` | CURRENT | остановить Recording и назвать файл |
| `POST /api/extended-clip/start` | TARGET | начать Extended Clip |
| `POST /api/extended-clip/finish` | TARGET | commit: остановить и собрать Extended Clip |
| `POST /api/extended-clip/cancel` | TARGET | отменить session до commit |

Тело трёх Extended Clip запросов пустое. Consumer **MUST NOT** передавать `session_id`.

## Семантика ответа action endpoint

Принятая асинхронная команда:

```json
{"ok": true, "accepted": true}
```

Безопасно отклонённая команда:

```json
{"ok": true, "accepted": false, "reason": "recording_already_active"}
```

Infrastructure failure:

```json
{"ok": false, "error": "Bridge is not connected"}
```

Consumer **MUST** после ответа продолжать читать `/api/status`. HTTP response подтверждает приём команды, а не завершение операции.

## Целевая часть `/api/status`

```json
{
  "backend": "ok",
  "bridge": "connected",
  "ui_state": "recording",
  "message": null,
  "extended_clip": {"active": true, "stage": "recording"},
  "obs": {
    "fresh": true,
    "recording_active": true,
    "recording_paused": false,
    "replay_buffer_active": true
  },
  "actions": {
    "save_moment": {"enabled": true, "reason": null},
    "save_recording": {"enabled": false, "reason": "extended_clip_active"},
    "extended_clip_start": {"enabled": false, "reason": "extended_clip_active"},
    "extended_clip_finish": {"enabled": true, "reason": null},
    "extended_clip_cancel": {"enabled": true, "reason": null}
  }
}
```

Существующее поле `phase` **SHOULD** сохраняться на время миграции старых consumers, но новые consumers **MUST** использовать `ui_state` и `actions`.

`message` предназначен для безопасного пользовательского сообщения. Технические exception strings и пути **MUST NOT** становиться обязательным UI-контрактом.

## Bridge endpoints

`GET /api/bridge/command`, `POST /api/bridge/command-result` и `POST /api/bridge/state` остаются внутренним transport contract.

BridgeCommandAction расширяется минимум командами:

- `extended_clip_start`
- `extended_clip_finish`
- `extended_clip_cancel`

Результаты sequence-команд **MUST** содержать только относящиеся к событию точные paths и metadata. Backend сам знает текущую session.

## Потеря связи

Если heartbeat Bridge или OBS state протух, все mutating actions **MUST** стать disabled. Активная Extended Clip session обрабатывается по [[06-failures-and-file-safety|fail-fast policy]].
