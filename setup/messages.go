package main

// The PowerShell command the site gives, for where this can't install.
const psCommand = "irm https://raw.githubusercontent.com/CustomFF/myfox/master/get.ps1 | iex"

var messages = map[string]map[string]string{
	"en": {
		"title":         "MyFox Setup",
		"preparing":     "Preparing…",
		"preparing_pct": "Preparing… %d%%",
		"starting":      "Starting the installer…",
		"cancel":        "Cancel",
		"failed":        "MyFox could not be installed.",
		"checksum":      "A downloaded file is damaged (checksum mismatch).",
		"arm":           "This installer is for x64 Windows. On ARM64, install MyFox from PowerShell:",
		"try_command":   "You can also install MyFox from PowerShell:",
		"no_localdata":  "%LOCALAPPDATA% is not set.",
		"installed":     "MyFox is already installed.",
		"check_updates": "Check for updates?",
	},
	"ru": {
		"title":         "Установка MyFox",
		"preparing":     "Подготовка…",
		"preparing_pct": "Подготовка… %d%%",
		"starting":      "Запуск установщика…",
		"cancel":        "Отмена",
		"failed":        "Не удалось установить MyFox.",
		"checksum":      "Загруженный файл повреждён (контрольная сумма не совпала).",
		"arm":           "Этот установщик для Windows x64. На ARM64 установите MyFox из PowerShell:",
		"try_command":   "MyFox можно установить и из PowerShell:",
		"no_localdata":  "Не задана переменная %LOCALAPPDATA%.",
		"installed":     "MyFox уже установлен.",
		"check_updates": "Проверить обновления?",
	},
}

var lang = "en"

func t(key string) string {
	if text, ok := messages[lang][key]; ok {
		return text
	}
	return messages["en"][key]
}
