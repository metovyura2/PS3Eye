# Ремонт драйвера камеры Sony PS Eye (Windows)

Набор скриптов, которым приводилась в рабочее состояние камера PS Eye
(`USB\VID_1415&PID_2000`). Нужны, если камера снова определится неверно.

## Симптомы, которые это лечит

- камера видна как «Составное USB устройство» с восклицательным знаком (код 10/28);
- DirectShow-устройство `PS3 Eye Universal` есть в списке, но кадры чёрные;
- в логах `libusb: error [init_device] device ... is no longer connected!`;
- `libusb: error [winusbx_open] ... [5] Отказано в доступе`.

## Причина

На интерфейсе камеры стоял драйвер **libusb-win32** (`libusb0.sys`, ставится Zadig),
а DirectShow-фильтр `PS3 Eye Universal` (Universal PS3 Eye Driver) работает через
**WinUSB** (libusb-1.0). Из-за конфликта фильтр устройство открывает, но данные не получает.

Рабочая конфигурация после ремонта:

| Интерфейс | Устройство | Драйвер | Служба |
| --- | --- | --- | --- |
| `MI_00` | PS3Eye Camera (класс Image) | `oem140.inf` / PS3EyeCamera.inf (Code Laboratories) | **WinUSB** |
| `MI_01` | USB Camera-B4.09.24.1 (класс MEDIA) | `wdma_usb.inf` (USB Audio) | usbaudio |
| родитель | Составное USB устройство | `usb.inf` | usbccgp |

## Порядок применения (каждый скрипт сам поднимает права через UAC)

```powershell
# 1. Бэкап состояния + скачивание PS3EyeInstallerBeta2.msi (если файла ещё нет)
powershell -NoProfile -ExecutionPolicy Bypass -File .\01_backup_and_download.ps1

# 2. Отключить камеру от USB, затем удалить «призрачные» устройства и Zadig-драйверы
powershell -NoProfile -ExecutionPolicy Bypass -File .\02_remove_devices_and_zadig.ps1

# 3. Установить Universal PS3 Eye Driver (WinUSB + DirectShow-фильтр)
powershell -NoProfile -ExecutionPolicy Bypass -File .\03_install_universal_driver.ps1

# 4. Подключить камеру в порт USB 2.0 и проверить состояние драйверов
powershell -NoProfile -ExecutionPolicy Bypass -File .\04_check_state.ps1

# 5. Если камера уже была подключена и «Составное USB устройство» висит с кодом 10
#    (после жёсткого завершения приложения, державшего WinUSB) — перезапустить устройство
powershell -NoProfile -ExecutionPolicy Bypass -File .\05_restart_camera.ps1

# 6. Проверка захвата в проекте
python ..\..\tools\probe_camera.py
```

Критерий успеха: в `temp\probe_report.txt` у всех режимов `непустых` = 60 и
`макс. яркость` значительно больше нуля.

## Важно

- Установщик `PS3EyeInstallerBeta2.msi` при повторном запуске может пропустить
  установку WinUSB-части (в логе `DIFXAPP: This is a no-op...`), если найдёт в системе
  драйвер Code Laboratories. В этом случае достаточно шагов 2 и 4: драйвер CL-Eye
  работает через службу WinUSB и подходит фильтру.
- Порт USB 2.0 предпочтителен; хабы и USB 3.0 дают срывы кадров.
- Камеру во время работ не должна держать ни одна программа (OBS, браузер и т. п.):
  устройства WinUSB открываются монопольно.
- Бэкапы исходного состояния — в `backup\` (`pnp_backup.txt`, `drivers_backup.txt`).
