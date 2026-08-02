# Сбои и сохранность файлов

[[README|К карте спецификации]] · Статус документа: **TARGET**

## Главное правило

> [!danger]
> Если успешный merge и его validation не завершены, SayClip **MUST NOT** удалять Replay или Recording ни при каких обстоятельствах.

На этапе полевого тестирования `delete_sources_after_success` **MUST** быть `false`: даже после успеха оба source-файла сохраняются.

## Матрица отказов

| Событие | Session | OBS Recording | Replay Buffer | Файлы | Merge |
|---|---|---|---|---|---|
| Cancel до commit | cancel | остановить, только если принадлежит session | не трогать | сохранить всё | нет |
| Ручной Stop Recording до Finish | cancel | уже остановлена | не трогать | сохранить всё | нет |
| Backend завершён/упал | fail-fast | Bridge **SHOULD** остановить owned Recording, если надёжно знает ownership | не трогать | сохранить всё | нет/прервать |
| Bridge script/OBS завершён | fail-fast | не предпринимать недоказуемых действий | состояние OBS как есть | сохранить всё | нет/прервать |
| Свет/процесс оборвался | session потеряна | неизвестно | неизвестно | ничего не удалять при следующем старте | нет recovery |
| Replay Save error/timeout | error | остановить только owned Recording | не трогать | сохранить созданное | нет |
| Overlap не найден | error | уже остановлена | не трогать | сохранить оба source + diagnostics | нет output |
| Format mismatch | error | уже остановлена | не трогать | сохранить оба source + diagnostics | нет output |
| FFmpeg/remux/validation error | error | уже остановлена | не трогать | сохранить sources + diagnostics; partial можно оставить для диагностики | failure |

## Shutdown contract

- Backend и Bridge loss **MUST** немедленно инвалидировать consumer actions.
- Система **MUST NOT** продолжать Extended Clip как будто orchestration остаётся надёжным.
- Bridge может остановить Recording при потере backend только если ownership текущей session доказан локально.
- OBS unload callback **MUST NOT** пытаться выполнить merge.
- Replay Buffer **MUST NOT** останавливаться автоматически ни Cancel, ни shutdown cleanup.

## Runtime JSON

Session snapshot **SHOULD** атомарно записываться в выделенной папке данных SayClip. Он нужен для расследования: session id, phase, ownership flags, known paths и timestamps.

При старте backend stale snapshot:

- **MUST** быть помечен abandoned/stale;
- **MUST NOT** возобновлять команды, merge или удаление;
- **SHOULD** быть сохранён как диагностика.

## Cleanup

Разрешено очищать только temporary-файлы, созданные текущей операцией и однозначно идентифицированные ею. Source Replay и Recording не являются temporary-файлами. Массовый поиск и удаление файлов по имени/времени **MUST NOT** использоваться.

