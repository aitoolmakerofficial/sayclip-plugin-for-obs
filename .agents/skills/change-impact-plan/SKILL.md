---

name: change-impact-plan
description: Analyze a requested code change and produce a read-only file impact table before implementation. Use when the user asks to estimate, assess, plan, or describe changes required for a coding task. Do not use this skill to implement changes.
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Change Impact Plan

## Purpose

Analyze a requested coding task, inspect the relevant repository files, and explain which files would need to be created, modified, or removed.

The primary result must be a file impact table.

This skill is analysis-only. It must never implement the proposed changes.

## Allowed actions

You may:

* read files in the current repository;
* search for filenames, symbols, classes, functions, configuration keys, and text;
* inspect imports and references;
* inspect the repository structure;
* compare the requested behavior with the existing implementation;
* identify relevant source files, tests, configuration files, types, documentation, and generated artifacts.

## Prohibited actions

You must not:

* create files;
* edit files;
* delete or rename files;
* apply patches;
* format files;
* execute Git commands;
* stage, commit, switch branches, merge, rebase, or push;
* run scripts;
* run package managers;
* install dependencies;
* run migrations;
* run build, test, lint, or formatting commands;
* invoke another agent that can modify the repository;
* begin implementation after producing the table.

These restrictions remain in effect even when the requested change appears simple or safe.

## Analysis procedure

1. Read the user's task carefully.
2. Inspect the repository structure.
3. Locate the current implementation related to the requested behavior.
4. Read the directly relevant files.
5. Follow important imports, references, interfaces, types, and configuration.
6. Determine the minimum coherent set of file changes.
7. Consider whether tests, types, configuration, documentation, or fixtures also require changes.
8. Produce the required table.
9. Stop and wait for explicit user approval.

Do not describe a file as affected merely because it is located near the relevant code. Every listed file must have a concrete reason for being included.

## Required output

Start with a brief interpretation of the requested task in no more than three sentences.

Then provide this exact table structure:

|  № | Имя файла | Изменения | Причина изменений |
| -: | --------- | --------- | ----------------- |

## Table rules

Create one row per affected file.

### №

Use consecutive numbers beginning with 1.

### Имя файла

Provide the path relative to the repository root.

Examples:

* `src/services/user-service.ts`
* `src/components/UserForm.tsx`
* `tests/user-service.test.ts`
* `src/types/user.ts`

Do not provide only a filename when the file is located inside a directory.

### Изменения

Begin with one of these words:

* **Создать**
* **Изменить**
* **Удалить**
* **Переименовать**

Then describe the proposed change concretely.

Mention relevant functions, classes, components, types, configuration sections, or responsibilities when they can be identified from the repository.

Good example:

> **Изменить:** добавить в `createUser` проверку уникальности email до сохранения пользователя и вернуть существующий тип ошибки конфликта.

Bad example:

> Изменить логику.

Do not write code in this column.

### Причина изменений

Explain how the file change contributes to the user's requested outcome.

The explanation must describe causality, not repeat the Changes column.

Good example:

> Без проверки на уровне сервиса два запроса могут создать пользователей с одинаковым email, что нарушает требование задачи.

Bad example:

> Потому что файл нужно изменить.

## New files

Include new files in the same table.

For a new file:

* provide the proposed repository-relative path;
* begin the Changes column with **Создать**;
* explain what responsibility the new file will have;
* explain why that responsibility should not be placed in an existing file.

Do not propose a new file when an existing file is the natural location for the change.

## Tests

Include test files when:

* existing behavior changes;
* a new branch or validation rule is introduced;
* a bug requires a regression test;
* an existing test must be updated;
* a new component or module needs coverage.

Describe which behavior or scenario the test should verify. Do not merely write “add tests.”

## Uncertain information

Do not invent files, symbols, APIs, or architectural conventions.

When the exact file cannot be identified after repository inspection:

1. do not present a guessed path as certain;
2. explain the uncertainty after the table;
3. identify what information is missing;
4. state what assumption was used.

## Minimal-change principle

Prefer the smallest coherent set of changes that fully addresses the task.

Do not include:

* unrelated refactoring;
* optional cleanup;
* formatting-only changes;
* dependency upgrades not required by the task;
* architectural redesign without a demonstrated need.

Optional improvements may be listed separately after the main table, clearly marked as optional. They must not be mixed with required changes.

## Final sections

After the table, include these sections only when relevant:

### Предположения

List assumptions that materially influenced the proposed changes.

### Открытые вопросы

List questions whose answers could change the affected files or implementation approach.

### Риски

Identify compatibility, data, security, performance, or migration risks.

Finish with this exact statement:

**Изменения не выполнялись. Ожидаю подтверждения таблицы перед реализацией.**

## Approval boundary

The following responses indicate that the user approves the proposed table:

* «Одобряю таблицу»
* «Приступай к реализации»
* «Реализуй предложенные изменения»
* another unambiguous approval referring to the table

Even after receiving approval, do not modify files while this skill is active.

Tell the user that the analysis phase is complete and that implementation requires switching to a write-enabled mode or implementation workflow.
