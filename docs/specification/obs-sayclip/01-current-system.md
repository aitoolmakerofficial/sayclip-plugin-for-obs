# Текущая система

[[README|К карте спецификации]] · Статус документа: **CURRENT**

Этот документ фиксирует базовое поведение, поверх которого теперь реализован экспериментальный MKV rollout Extended Clip. Нормативное описание нового use case находится в [[03-extended-clip]].

## Реализованный поток

1. Consumer вызывает `POST /api/save/moment` или `POST /api/save/recording`.
2. `BackendApi` создаёт одну `BridgeCommand` и возвращает `202`.
3. OBS Bridge опрашивает `GET /api/bridge/command` каждые 750 ms.
4. Для Moment Bridge сохраняет Replay Buffer; для Recording — останавливает уже активную Recording.
5. OBS frontend event даёт путь готового файла.
6. Bridge отправляет результат в `POST /api/bridge/command-result`.
7. Backend создаёт `NamingJob`: listening → transcribing → renaming → done/error.

## Текущие внутренние фазы

`OperationPhase` содержит:

`idle`, `command_sent`, `waiting_for_obs`, `waiting_for_file`, `listening`, `transcribing`, `renaming`, `done`, `error`.

Поле `phase` сохранено в `/api/status` для обратной совместимости. Dock и обновлённый Stream Deck contract используют отдельный стабильный `ui_state`, поэтому внутренний workflow больше не является их основным presentation contract.

## Текущие действия

| Action | Endpoint | Условие доступности при свежем OBS state |
|---|---|---|
| `save_moment` | `POST /api/save/moment` | Replay Buffer активен |
| `save_recording` | `POST /api/save/recording` | Recording активна |

Оба действия блокируются при активной обычной команде/job или отключённом Bridge. Если OBS heartbeat устарел, текущий код оставляет действия разрешёнными и позволяет Bridge вернуть фактическую ошибку.

## Текущий heartbeat

Bridge отправляет `recording_active`, `recording_paused`, `replay_buffer_active`, последние recording/replay paths. Backend считает Bridge и OBS state свежими 3 секунды.

## Текущие ограничения базового потока

- `JobType` также поддерживает `extended_clip`.
- Extended Clip имеет Start/Finish/Cancel endpoints, внутреннюю session и MKV merge service.
- JobStore и BridgeCommand хранятся только в памяти; Extended Clip runtime JSON является диагностикой, а не recovery store.
- Dock содержит Save Clip, Save Recording и одну контекстную кнопку Extended Clip.
- Stream Deck plugin отсутствует в этом репозитории; здесь находится только Python contract для будущей интеграции.
