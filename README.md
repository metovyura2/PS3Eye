# PSEyes — таймлапс с камеры Sony PS Eye для стола 3D-принтера

> **PSEyes** — timelapse camera app for the Sony PlayStation Eye (PS3) webcam on Windows.
> Live preview (PyQt6 + OpenCV/DirectShow), interval JPEG capture, MP4 assembly via ffmpeg
> (H.264). Built for 3D-printer table timelapse; includes PS Eye driver repair scripts
> (Windows error code 10 / WinUSB), camera hot-recovery and manual capture properties.
>
> **Keywords:** ps3 eye, ps3eye, playstation eye, sony ps eye, timelapse, time-lapse,
> 3d printing, 3d printer, octolapse, python, pyqt6, opencv, directshow, ffmpeg, webcam,
> usb camera, h264, windows, winusb, camera, video capture.

Программа принимает видео с камеры Sony PS Eye (PS3) напрямую, показывает превью
и пишет таймлапс: кадры сохраняются в JPEG по таймеру, затем собираются в MP4 (H.264).

## Требования

- Windows 10/11 x64
- Python 3.11+ (`python --version`)
- ffmpeg в `C:\ffmpeg\bin\ffmpeg.exe` или в `PATH`
- Драйвер камеры: **Universal PS3 Eye Driver** (jkevin/PS3EyeDirectShow)
  - установщик: `PS3EyeInstallerBeta2.msi`
  - https://github.com/jkevin/PS3EyeDirectShow/releases
  - После установки камера видна как DirectShow-устройство `PS3 Eye Universal`.
  - **Рабочая конфигурация** (проверена): интерфейс `MI_00` — устройство «PS3Eye Camera»
    на драйвере `PS3EyeCamera.inf` (Code Laboratories) со службой **WinUSB**.
  - **Нельзя** ставить на камеру Zadig-овский драйвер libusb-win32 (`libusb0.sys`):
    фильтр работает через WinUSB и с ним отдаёт чёрные кадры.
  - Если камера определилась как «Составное USB устройство» с ошибкой — используйте
    готовые скрипты ремонта: `tools\driver_fix\` (см. `tools\driver_fix\README.md`).

Установка зависимостей:

```powershell
python -m pip install -r requirements.txt
```

## Запуск

```powershell
run.bat
```

или

```powershell
python main.py
```

## Как пользоваться

1. Подключите камеру к USB (лучше USB 2.0 порт, без хабов).
   Камера открывается монопольно: не держите её одновременно в OBS, браузере и т. п.
2. Запустите программу — в списке устройств выберите `PS3 Eye Universal`,
   при необходимости нажмите «Обновить».
3. Настройте съёмку:
   - **Разрешение** — 640x480 (рекомендуется) или 320x240;
   - **FPS камеры** — 30 (60 для 640x480 может дёргаться);
   - **Интервал съёмки** — как часто сохраняется кадр (например, 10 с);
   - **FPS видео** — частота кадров готового MP4;
   - **Качество JPEG**, **Поворот кадра** (0/90/180/270);
   - **Папка сессий**, кодек (`libx264` — надёжный, `h264_nvenc` — быстрее на NVIDIA).
4. «Свойства камеры» — открывает диалог драйвера (экспозиция, усиление, баланс белого).
   Настраивайте при выключенном свете стола: автобаланс белого на PS Eye слабый.
5. **Старт** — начинается съёмка кадров, **Пауза** — пауза, **Стоп** — остановка.
   При включённой галочке MP4 собирается автоматически после остановки.
6. Кнопка **Собрать MP4** доступна и отдельно — для повторной сборки или если
   автосборка выключена.

Результат: `sessions/<дата_время>/timelapse.mp4`, кадры — в `sessions/<дата_время>/frames/`,
параметры сессии — в `session.json`.

## Длительность видео

Длительность = число кадров / FPS видео. Пример: интервал 10 с, съёмка 2 часа
(720 кадров), FPS видео 30 → ролик 24 секунды.

## Диагностика

```powershell
python tools/probe_camera.py
```

Скрипт выводит список устройств, режимы камеры, реальную скорость захвата и
среднюю яркость кадров, отчёт сохраняет в `temp/probe_report.txt`.

Сборка видео из уже готовых кадров:

```powershell
python tools/build_from_frames.py sessions\2026-09-30_20-00-00 --fps 30 --codec libx264
```

## Типичные проблемы

| Симптом | Причина / решение |
| --- | --- |
| Устройство `PS3 Eye Universal` не в списке | Не установлен драйвер (PS3EyeInstallerBeta2.msi) или камера не в USB |
| Превью чёрное, в журнале «Чёрный кадр» | Камеру держит другая программа (OBS, браузер) — закройте её; либо на камере стоит libusb-win32 от Zadig: см. `tools\driver_fix\` |
| Превью чёрное, в консоли `libusb: ... ReadPipe/WritePipe failed`, у «Составное USB устройство» код 10 | USB-композит камеры не запущен. Переподключите камеру в порт USB 2.0 (без хаба) или запустите `tools\driver_fix\05_restart_camera.ps1` (нужны права админа); если не помогло — перезагрузка ПК |
| Камера как «Составное USB устройство» с ошибкой | Конфликт драйверов: выполните скрипты из `tools\driver_fix\` (01 → 04) |
| Низкий fps, рывки | Порт USB 3.0/хаб; поставьте 640x480@30 или 320x240 |
| Ошибка сборки ffmpeg | Проверьте путь к ffmpeg (`C:\ffmpeg\bin\ffmpeg.exe`) и наличие кодеков |
| Видео «прыгает» по яркости | Отключите автокоррекцию в «Свойства камеры», зафиксируйте экспозицию |
| Диагностика показывает `mean 0.0` и «Отказано в доступе» | Камеру уже держит приложение — закройте PSEyes и повторите |
