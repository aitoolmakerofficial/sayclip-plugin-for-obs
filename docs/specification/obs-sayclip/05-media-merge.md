# Media merge

[[README|К карте спецификации]] · Статус документа: **TARGET, алгоритм подтверждён probe**

## Инвариант

Merge **MUST** работать через packet stream copy (`-c copy`). Audio и video **MUST NOT** перекодироваться.

## Поиск overlap

Доказанный экспериментом алгоритм:

1. Прочитать начало Recording, начиная с первого decodable video GOP.
2. Найти последовательность точных packet hashes в хвосте Replay.
3. Проверить соответствующий overlap для каждого audio track.
4. Взять Replay только до найденного GOP и добавить Recording целиком.

Направление поиска **MUST** оставаться «первые packets Recording внутри хвоста Replay». Требование найти целую последнюю секунду Replay неверно: успешный реальный прогон имел overlap около 0.417 s.

Для MVP:

- читать не более последних 3 s Replay и первых 3 s Recording;
- требовать минимум 16 совпавших video packets;
- проверять минимум 8 packets на каждом audio track;
- ожидаемый orchestration overlap настраиваемый, ориентир около 1.5 s.

Если overlap не найден, blind concat **MUST NOT** выполняться.

## Совместимость inputs

- Расширения двух входных файлов **MUST** совпадать без учёта регистра.
- Фактические containers **MUST** соответствовать ожидаемому типу; совпадающих suffix недостаточно.
- Video codec, codec extradata, размеры и существенные stream parameters **MUST** быть совместимы.
- Количество и layout audio streams **MUST** совпадать.
- Различающийся container time base сам по себе может быть нормализован remux-операцией и не требует transcoding.

## Output format

| Inputs | Final output текущего полевого этапа | Pipeline |
|---|---|---|
| MKV + MKV | MKV | merge в temporary MKV → validate → atomic finalize |
| MP4 + MP4 | MKV | merge в temporary MKV → validate → atomic finalize |
| разные расширения | нет output | явная format mismatch error |

На текущем полевом этапе output всегда является настоящим MKV. Это не перекодирование: compressed AV1/AAC packets копируются без изменения. MP4 inputs не переименовываются и не удаляются.

Файл с расширением `.mp4`, содержащий Matroska bytes, **MUST NOT** считаться MP4. Ранний `replay_overlap_probe.py` мог создать такой mislabeled output; этот результат доказал бесшовность packets, но не MP4 support.

Поддержка настоящего MP4 остаётся следующим **TARGET**: после накопления библиотеки retained sources выполняется MKV → MP4 remux `-c copy`, затем отдельная validation и ручная полевая проверка до заявления production support.

## Validation

До публикации output система **MUST** проверить:

- container и расширение;
- ожидаемые video/audio streams и codecs;
- длительность относительно входов и удалённого overlap;
- отсутствие критических timestamp/corruption diagnostics;
- декодируемость короткого окна вокруг seam.

Output сначала пишется в уникальный `.partial`/temporary path и только после validation атомарно получает финальное имя.

## Диагностика

Diagnostics JSON **SHOULD** содержать input probes, packet match summary, seam location, stream verification, FFmpeg commands/versions, output probe и validation result. Он **MUST NOT** использоваться для автоматического recovery после рестарта.
