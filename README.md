<!-- Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:15:49 -->
# EDHUD — один оверлей из трёх программ

Оверлей-полоса в верхней части экрана (как у SrvSurvey), которая показывает
маршрут (как Exploration Buddy/EDEB), наличие биологии и геологии на теле,
виды-предсказания, прогресс проб, дистанцию до «клональной колонии» и стоимость
данных с множителями первооткрывателя. Работает под Windows (основная цель),
запускается и на macOS/Linux в терминальном режиме.

```
███████████████·······························   ← прогресс маршрута
МАРШРУТ 1/3  →  HIP 36601 (A · 50.0 ly)   осталось 2 · 115.4 ly  заправка ✔
ТЕЛО Synuefe GG-O c22-4 1 · Icy body · 1 180 ls   БИО 2 (Bacterium, Fungoida) · гео 1   DSS ✔   ≈1.42 Mcr ×2.6
────────────────────────────────────────────────────────────────────────
● Bacterium Cerbrus - Lime  2/3  ≈1.69 Mcr
стоимость: скан ≈120 Kcr · с DSS ≈1.42 Mcr · ×2.6 за первое открытие
предсказание: Bacterium
≈ Bacterium Acies - Lime  1.00 Mcr
био в системе: 2
• Synuefe GG-O c22-4 2 a  1 сигн. (Osseus)   DSS ✗   [spansh]   2 410 ls
система: 12 тел · данных ≈3.4 Mcr · с DSS ≈9.8 Mcr · EDSM ≈7.7 Mcr / с картами ≈9.1 Mcr
сессия: 2 прыжк. · скан 120 Kcr · DSS 1.3 Mcr · био ≈1.69 Mcr
```

## Что взято из каждого проекта

| Проект | Что взято |
|---|---|
| **EDMarketConnector** (EDCD, Python) | Чтение `Journal*.log` (самый свежий файл, дочитывание с позиции, replay при старте), `Status.json`/`NavRoute.json` по mtime, поиск каталога журналов, разбор битов `Flags` статуса. |
| **SrvSurvey** (njthomson, C#) | Оверлей: окно без рамки, always-on-top, сквозное для мыши (`WS_EX_TRANSPARENT`/`WS_EX_NOACTIVATE`). Движок предсказания биологии (`BioCriteria`/`BioPredictor`) и **данные** `bio-criteria/*.json`, таблица родов и дистанции проб, карта галактических регионов, справочник кодекса (имена и стоимость Vista Genomics), **формула стоимости скана** (`Util.GetBodyValue`), Guardian bubble, кэш систем. |
| **EDDiscovery** (C#) | Идеи по маршрутам: `NavRoute.json` как источник, прогресс/остаток, плоттеры (Spansh Galaxy Plotter), маршрут отдельно от игры. |
| **EDEB / Exploration Buddy** (CMDR Panostrede) | Набор функций и вид HUD: маршрут с прогрессом, блокировка/импорт маршрута, предсказание видов, статус анализа (1/3 → готово), индикатор клональной колонии, ценность проб, HUD поверх игры, **догрузка тел, открытых другими командирами**, «?» для тел без данных. |

## Возможности

* **Оверлей сверху экрана**: полоса по центру верхнего края, прозрачность, цвета и
  шрифт в конфиге. Windows: иконка в трее (ПКМ: оверлей, карта Spansh/EDSM,
  настройки, выход); `F8` — подробности, `F9` — сквозной режим мыши, `F10` —
  скрыть/показать, `F12` — выход; при выключенном сквозном режиме — кнопка × и
  ПКМ по полоске. Окно удерживается поверх всех каждые 2 секунды,
  DPI-awareness (Per-Monitor v2), не забирает фокус у игры.
* **Настройки** (трей → Настройки): каталог журналов, сеть, EDSM/Spansh/EDDN,
  необязательный EDSM API key, голос, прозрачность/ширина оверлея. Файл:
  `%LOCALAPPDATA%\EliteDangerousHUD\config.json`.
* **Окно EDHUD** (трей → «Окно EDHUD»): вкладки Route и Bodies — список тел
  системы (тип, атмосфера, био/гео, DSS, оценка Cr, первооткрытие, дистанция).
  Оверлей сверху экрана при этом остаётся.
* **Голос** (Windows SAPI, русский): «Биологический сигнал найден»,
  «Звёздная система открыта вами». Включается после дочитывания журнала
  (replay не озвучивается). Флаги в настройках.
* **Маршрут** (как Buddy): прогресс `1/3`, следующая система, класс звезды,
  расстояние, остаток прыжков/ly, «заправка/не заправка», топливо, метка
  залоченного маршрута. Lock/import/export маршрута, Spansh Galaxy Plotter.
* **Биология на теле**: био/гео-сигналы, роды после DSS, статус DSS, предсказание
  genus/species/variant по данным тела (атмосфера, температура, давление,
  гравитация, вулканизм, материалы, тип звезды, регион, расстояние до туманностей,
  Guardian bubble).
* **Пробы**: `1/3 → 2/3 → готово`, дистанция от предыдущей пробы и нужный интервал
  рода (`605 м/500 м`, зелёным когда можно брать следующую).
* **Данные других командиров**: EDSM + Spansh (`remote/`) и **живой фид EDDN**
  (`edhud/eddn.py`): собственный ZMTP-клиент подписывается на
  `tcp://eddn.edcd.io:9500`, фильтрует сообщения по текущей системе и сразу
  подмешивает `Scan`, `FSSBodySignals`, `SAASignalsFound`, `SAAScanComplete`.
  pyzmq не обязателен (если установлен — используется он). Тела из чужих данных
  помечаются `[EDSM]` / `[spansh]` / `[EDDN]`, тела без данных — «?» (как в EDEB).
  Кэш на диск, работа офлайн по кэшу, флаги `--offline`, `--no-remote`, `--no-eddn`.
* **Стоимость**: скан и скан+DSS для каждого тела, множители первооткрывателя
  (×2.6) и картографии (×3.33/×8.1/×3.7 + бонус Odyssey и +25 % за эффективный
  DSS), итоги по системе, суммы за сессию, реальные выплаты из
  `SellExplorationData`/`SellOrganicData`.
* **Биология: бонус First Logged**. Vista Genomics платит базовую стоимость вида,
  а если пробу ещё никто не сдавал — **×5** (это не «первый футфол»: футфол даёт
  только метку на планете). Признак берётся из журнала
  (`ScanOrganic.WasLogged`), поэтому в HUD видно `≈8.45 Mcr ×5 First Logged` или
  `(base, First Logged ?)`, если игра поле не прислала. Фактические суммы с
  бонусами всегда видны после продажи (`SellOrganicData`).
* **Legacy 3.8**: определяется по `Fileheader/LoadGame` (`gameversion` 3.x) —
  отключаются Odyssey-бонус в стоимости, био-прогноз и догрузка EDSM/EDDN
  (там только Live-данные), в HUD появляется метка `[Legacy 3.8]`.
* **Память**: просканированные системы кэшируются в `…/EliteDangerousHUD/systems/*.json`.
* **Терминальный режим** (`--tui`) и демо-режим на синтетическом журнале.

## Установка и запуск (Windows)

Нужен Python 3.10+ с tkinter (официальный установщик python.org, галочка «tcl/tk»).
Внешних пакетов нет.

```bat
python run.py                 :: оверлей, каталог журналов ищется сам
python run.pyw                :: то же без консольного окна (двойной клик)
python run.py run --journal-dir "C:\Users\me\Saved Games\Frontier Developments\Elite Dangerous"
python run.py run --tui       :: HUD в терминале
python run.py run --demo      :: демо на синтетическом журнале
python run.py run --offline   :: без сети (нет EDSM/Spansh/EDDN и каталога туманностей)
python run.py dump            :: один кадр HUD в консоль
python run.py remote "HIP 36601"   :: что EDSM/Spansh знают о системе
python run.py eddn --seconds 20    :: проверить живую подписку EDDN
python run.py eddn --system "Sol"  :: только сообщения по системе
```

Каталог журналов по умолчанию:

* Windows: `%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous`
* macOS: `~/Library/Application Support/Frontier Developments/Elite Dangerous`
* Linux/Proton: `…/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous`

Настройки: `config.json` (Windows `%LOCALAPPDATA%\EliteDangerousHUD`), там же кэш
систем (`systems/`), ответы EDSM/Spansh (`remote/`) и залоченный маршрут.

### Эксклюзивный fullscreen

Полноэкранный режим DirectX не позволяет рисовать поверх себя никаким сторонним
окнам — это ограничение драйвера, а не приложения. Сделано всё, что можно:
окно помечается `WS_EX_TOPMOST` и **переставляется поверх каждые 2 секунды**
(игра и система любят сбрасывать topmost), плюс в HUD появляется подсказка
`Alt+Enter (Borderless)`, когда в фокусе полноэкранное окно. В Borderless/Windowed
оверлей виден всегда.

### Сборка exe (portable + установщик)

Нужен Python 3.10+ с tkinter. Для установщика — [Inno Setup 6](https://jrsoftware.org/isdl.php)
(`winget install --id JRSoftware.InnoSetup -e`).

```bat
build_windows.bat
```

На выходе в `dist\`:

| Файл | Назначение |
|---|---|
| `EDHUD-portable\EDHUD.exe` | Portable standalone: один файл, копируешь на другой ПК и запускаешь |
| `EDHUD-portable.zip` | То же в архиве |
| `EDHUD\` | Папка с exe + библиотеками (основа для установщика) |
| `EDHUD-Setup-<ver>.exe` | Windows-установщик (ярлыки, опционально автозапуск) |

Python на целевом ПК **не нужен**: внутри — интерпретатор, tkinter и `data/`.
Настройки и кэш пишутся в `%LOCALAPPDATA%\EliteDangerousHUD` (не в папку программы).
Автозапуск без установщика: ярлык на `EDHUD.exe` в `shell:startup`.

## Маршруты

```bash
python run.py lock                    # залочить текущий маршрут игры
python run.py unlock                  # снова показывать маршрут игры
python run.py import-route route.csv  # импорт текста/CSV Galaxy Plotter
python run.py plot "Sol" "Colonia" --range 60 --efficiency 60
python run.py export-route route.json
```

Залоченный/построенный маршрут живёт в `route_locked.json` и имеет приоритет над
маршрутом игры; прогресс считается по нему. `plot` работает через
`https://spansh.co.uk/api/route` (асинхронная задача + опрос результата).

## Стоимость данных

Формула и множители — из темы «Exploration Value Formulae» (порт
`Util.GetBodyValue` из SrvSurvey):

```
value = (k + k*q*mass^0.2) * mappingMultiplier
mappingMultiplier = 3.6996 (первый открыватель + первый картограф)
                  | 8.0956 (первый картограф)
                  | 3.3333 (картография не первая)
+ бонус Odyssey (30 % или минимум 555), ×1.25 за эффективный DSS,
не ниже 500, затем ×2.6 за первое открытие.
Звёзды: value = kk + mass*kk/66.25 (kk: 1200 / 22628 для NS/BH / 14057 для W*).
```

HUD показывает для текущего тела `≈скан` (или `≈` после DSS) и `×2.6`, если тело
ещё никем не открыто; в подробностях — разбивку, кто открыл/картографировал; в
строке «система» — суммы по своим данным и оценку EDSM; в строке «сессия» —
накопленные скан/DSS/биология и реально проданные данные. Для тел, известных
только по EDSM/Spansh/EDDN, множитель первого картографа не применяется (мы не
знаем, картографировали ли их уже), поэтому оценка консервативная.

### Биология: First Logged

Vista Genomics платит базовую стоимость вида; если пробу ещё никто не сдавал, за
«First Logged» начисляется ещё четыре базовые стоимости, то есть **×5**. Это не
«первый футфол»: футфол только ставит метку на планете и денег не даёт (в HUD он
показывается отдельно — «чужого футфола нет: шанс на ×5 First Logged»).
Признак берётся из журнала `ScanOrganic.WasLogged` (`false` → бонус будет).
Если игра поле не прислала, HUD пишет `(base, First Logged ?)`; после продажи
показываются фактические суммы из `SellOrganicData` (`Value` + `Bonus`).

## Как это устроено

```
Journal*.log / Status.json / NavRoute.json
        │  edhud/journal.py
        ▼
edhud/model.py   GameState: система, тела, сигналы, пробы, статус, маршрут, деньги
        │        ├── edhud/bio.py     критерии -> предсказания (небулы, Guardian)
        │        ├── edhud/values.py  стоимость скана/картографии + множители
        │        ├── edhud/remote.py  EDSM + Spansh -> тела других командиров
        │        ├── edhud/eddn.py    живой фид EDDN (+ edhud/zmtp.py, если нет pyzmq)
        │        ├── edhud/galaxy.py  туманности и Guardian bubble
        │        ├── edhud/codex.py   имена/стоимость/дистанции родов
        │        ├── edhud/regions.py регион галактики по координатам
        │        └── edhud/store.py   кэш систем на диске
        ▼
edhud/hudmodel.py  HudView: строки и сегменты (без UI)
        │
        ├── edhud/overlay.py  tkinter-окно сверху экрана (+ edhud/winapi.py)
        └── edhud/tui.py      тот же вид в терминале
```

`edhud/app.py` — связка: watcher, кэш, фоновая догрузка EDSM/Spansh, поток EDDN,
цикл обновления, горячие клавиши. `edhud/winapi.py` — DPI, click-through, удержание
topmost, детект полноэкранного окна.

### EDDN

`edhud/zmtp.py` — минимальный ZMTP 3.1-подписчик (приветствие, READY, SUBSCRIBE,
PING/PONG): EDDN отдаёт zlib-сжатый JSON, поэтому pyzmq не нужен. Если pyzmq
установлен, `edhud/eddn.py` использует его. Фильтр по системе строится по
`SystemAddress`/`StarSystem`, применяются `Scan`, `FSSBodySignals`,
`SAASignalsFound`, `SAAScanComplete` — только для дополнения недостающего, свои
данные никогда не перезаписываются. Проверка: `python run.py eddn --seconds 20`.

### Legacy 3.8

Версия берётся из `Fileheader`/`LoadGame` (`gameversion`: `3.8.x` → Legacy,
`4.x` → Live/Odyssey). В Legacy: нет Odyssey-бонуса в стоимости (множители
картографии и ×2.6 остаются), био-прогноз отключён, EDSM/Spansh/EDDN не
догружаются (там только Live-данные) — при желании включается
`remote_in_legacy` в `config.json`. В HUD — метка `[Legacy 3.8]` и подсказка.

### Предсказание биологии

`data/bio-criteria/*.json` — дерево условий на каждый род (SrvSurvey, GPLv3).
Клаузы: `temp [146 ~ 196]`, `atmosType [Neon]`, `mats &[Carbon,Sulphur]`,
`mats ![Iron,Nickel]`, `atmosComp [Neon >= 100 | Nitrogen >= 46]` (внутри одной
клаузы составы объединяются через «или»), `regions [...]`, `nebulae [ ~ 160]`,
`guardian [true]`, `# комментарий`. Свойства берутся из `Scan`, у тел из EDSM —
из ответа API (гравитация g → м/с², давление bar → Па, температуры K).

Каталог туманностей (`edastro.com/mapcharts/files/nebulae-coordinates.csv`)
скачивается один раз в кэш; Guardian bubble — две большие сферы по 750 ly
(Gamma Velorum, HEN 2-333) и шесть по 100 ly.

## Тесты и разработка

```bash
python -m unittest discover -s tests     # 81 тест: критерии, регионы, стоимость,
                                         # EDSM/Spansh, EDDN/ZMTP, Legacy, конвейер
python tools/inspect_bio.py              # свойства тела и предсказания по журналу
python tools/inspect_remote.py "HIP 36601"  # предсказания по чужим данным
python tools/debug_bio.py Bacterium      # трассировка критериев
python tools/render_test.py              # отрисовка оверлея без игры (canvas -> postscript)
python tools/eddn_probe.py               # что идёт в живом фиде EDDN (нужен pyzmq)
python tools/check_imports.py            # неиспользуемые импорты
```

## Данные, лицензии, благодарности

* `data/bio-criteria/*.json` — из [SrvSurvey](https://github.com/njthomson/SrvSurvey)
  (GPL-3.0), автор njthomson и сообщество.
* `data/galaxy_regions.json` — карта регионов из
  [klightspeed/EliteDangerousRegionMap](https://github.com/klightspeed/EliteDangerousRegionMap)
  (MIT), упакована в RLE.
* `data/codex_ref.json` — выжимка из справочника кодекса Canonn (через SrvSurvey).
* Формула стоимости — [Exploration Value Formulae](https://forums.frontier.co.uk/threads/exploration-value-formulae.232000).
* Данные систем — EDSM (`edsm.net/api-system-v1/*`), Spansh
  (`spansh.co.uk/api/bodies/search`) и живой EDDN (`tcp://eddn.edcd.io:9500`).
* Идеи и форматы журналов — [EDMarketConnector](https://github.com/EDCD/EDMarketConnector),
  [EDDiscovery](https://github.com/EDDiscovery/EDDiscovery),
  [Exploration Buddy](https://www.panostrede.de/EDEB/).

Код распространяется по GPL-3.0 (из-за данных критериев), см. `LICENSE`.
Пересобрать `data/`: `sh tools/fetch_reference.sh && python tools/vendor_data.py`.

## Чего пока нет

* **Встроенной галактической карты нет** — Spansh/EDSM открываются в браузере из
  трея. API: догрузка тел и Galaxy Plotter (`python run.py plot A B`). Ключ EDSM
  для чтения тел **не нужен** (поле в настройках — для личных API EDSM).
* Вкладки Surroundings / History (как в EDEB) пока нет — только Route и Bodies.
* Био-прогноз опирается на Odyssey-критерии: в Legacy он отключён (там другой
  набор организмов), в Live работает как подсказка, а не гарантия.
* Оценка стоимости скана звезды не включает бонус «эффективного» DSS (у звёзд
  его нет), а у тел, известных только по чужим данным, не применяется множитель
  первого картографа — намеренно консервативно.
* EDSM/Spansh/EDDN содержат только Live-данные: в Legacy догрузка выключена
  (можно включить `remote_in_legacy`, но данные будут от Live-вселенной).
* Каталог туманностей и Guardian bubble нужны для части критериев: сам каталог
  качается с edastro.com, без сети критерии `nebulae [...]` не срабатывают.
