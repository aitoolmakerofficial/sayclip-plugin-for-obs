# Реестр решений

[[README|К карте спецификации]]

## Принято

| Решение | Обоснование |
|---|---|
| Пользовательское и кодовое имя — Extended Clip | Не путать use case с общей Recording или абстрактной Sequence |
| Три endpoints: Start, Finish, Cancel | Явная семантика и отсутствие toggle-race |
| Клиент не передаёт session id | В системе только одна активная session; backend владеет идентичностью |
| Внутренние фазы не являются UI contract | Consumers нужны только Recording и Processing плюс общие состояния |
| Доступность всех кнопок приходит в `actions` | Dock и Stream Deck ведут себя одинаково |
| `reason` — machine code для tooltip/toast | Не смешивать unavailable reason с глобальным статусом |
| Отдельного debounce пока нет | Атомарные guards достаточно для MVP; сложный queued finish не нужен |
| Cancel доступен только до Finish commit | После начала stop/merge операция уже необратимо перешла в processing |
| Manual Recording Stop до Finish означает Cancel | Пользователь не запросил merge через endpoint |
| Replay Buffer никогда автоматически не останавливается | Это независимый долгоживущий OBS resource |
| Save Clip допустим в `capturing` | Он использует продолжающий работать Replay Buffer |
| Очередей операций нет | Явный `operation_busy` проще и безопаснее MVP |
| Поиск overlap ограничен хвостом/началом по 3 s | Ограничивает память и подтверждено назначением orchestration |
| Merge и MP4 remux только `-c copy` | Никакого transcoding |
| Sources пока не удаляются даже после успеха | Полевое тестирование и приоритет сохранности данных |
| Recovery после рестарта отсутствует | Stale JSON только для диагностики |
| Dock пока получает одну новую contextual кнопку | Полный layout и отдельный Cancel control будут решены позднее |
| Первый production rollout всегда публикует MKV | Сначала проверяем orchestration и seam на библиотеке реальных MP4/MKV sources; настоящий MP4 remux добавляется следующим этапом |

## Отложено

- Финальная компоновка четырёх действий в OBS Dock.
- UI-вход для Cancel в Dock; API уже обязателен.
- Конкретный SDK/framework и финальный визуальный стиль внешнего Stream Deck plugin; функциональный контракт описан в [[08-stream-deck-plugin-tz]].
- Включение удаления sources после успешной длительной полевой проверки.
- Recovery/resume abandoned session.
- Очередь обычного Save Clip и Finish.
- Точный набор поддерживаемых containers/codecs после полевых тестов.

## Требует экспериментального подтверждения

- Настоящий MP4 output: temporary validated MKV → `ffmpeg -c copy` MP4 → validation на реальных OBS AV1 + multi-track AAC files.
- Достаточность 3-second match windows для разных encoder/keyframe configurations.
- Надёжный способ доказать ownership Recording при потере backend.

## Порядок полевого rollout

1. Core Extended Clip + настоящий MKV output через stream copy.
2. Накопление replay/recording/merged файлов; sources не удаляются.
3. Отдельный MP4 remux experiment на собранной библиотеке.
4. Включение MP4 output только после container и seam validation.
