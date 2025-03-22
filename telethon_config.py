import os
import json
import logging

logger = logging.getLogger(__name__)

# Путь к файлу конфигурации Telethon
TELETHON_CONFIG_FILE = "telethon_settings.json"

# Значения по умолчанию
DEFAULT_CONFIG = {
    "api_id": 0,  # API ID (получите на my.telegram.org/apps)
    "api_hash": "",  # API Hash (получите на my.telegram.org/apps)
    "session_name": "tg_session",  # Имя файла сессии Telethon
    "check_comments": True,  # Проверять ли наличие открытых комментариев
    "skip_channels_without_comments": True,  # Пропускать ли каналы без комментариев
    "connection_retries": 5,  # Количество попыток подключения при ошибке
    "request_delay": 1.5  # Задержка между запросами в секундах
}


def load_telethon_config() -> dict:
    """
    Загружает конфигурацию Telethon из файла или создает новый файл, если он не существует
    
    Returns:
        dict: Словарь с настройками Telethon
    """
    # Проверяем, существует ли файл конфигурации
    if not os.path.exists(TELETHON_CONFIG_FILE):
        # Если файла нет, создаем его с настройками по умолчанию
        with open(TELETHON_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=4)
            
        logger.info(f"Создан файл конфигурации Telethon {TELETHON_CONFIG_FILE} с параметрами по умолчанию")
        logger.warning("Необходимо указать api_id и api_hash в файле настроек Telethon")
        return DEFAULT_CONFIG
    
    # Загружаем конфигурацию из файла
    try:
        with open(TELETHON_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        logger.info(f"Загружена конфигурация Telethon из файла {TELETHON_CONFIG_FILE}")
        
        # Проверяем наличие API ID и Hash
        if not config.get('api_id') or not config.get('api_hash'):
            logger.warning("API ID или API Hash для Telegram не указаны в конфигурации")
        
        return config
    except Exception as e:
        logger.error(f"Ошибка при загрузке файла конфигурации Telethon: {e}")
        return DEFAULT_CONFIG


def save_telethon_config(config: dict) -> bool:
    """
    Сохраняет конфигурацию Telethon в файл
    
    Args:
        config: Словарь с настройками
        
    Returns:
        bool: True если сохранение успешно, иначе False
    """
    try:
        with open(TELETHON_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        
        logger.info(f"Конфигурация Telethon сохранена в файл {TELETHON_CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении файла конфигурации Telethon: {e}")
        return False


# Загружаем конфигурацию при импорте модуля
telethon_config = load_telethon_config()

# Экспортируем настройки для удобного импорта
API_ID = telethon_config.get('api_id', DEFAULT_CONFIG['api_id'])
API_HASH = telethon_config.get('api_hash', DEFAULT_CONFIG['api_hash'])
SESSION_NAME = telethon_config.get('session_name', DEFAULT_CONFIG['session_name'])
CHECK_COMMENTS = telethon_config.get('check_comments', DEFAULT_CONFIG['check_comments'])
SKIP_CHANNELS_WITHOUT_COMMENTS = telethon_config.get('skip_channels_without_comments', DEFAULT_CONFIG['skip_channels_without_comments'])
CONNECTION_RETRIES = telethon_config.get('connection_retries', DEFAULT_CONFIG['connection_retries'])
REQUEST_DELAY = telethon_config.get('request_delay', DEFAULT_CONFIG['request_delay']) 