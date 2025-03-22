import json
import time
import requests
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from bs4 import BeautifulSoup
import re
import os
from telethon.sync import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
import asyncio
import logging
from telethon_config import (
    API_ID, API_HASH, SESSION_NAME, CHECK_COMMENTS, 
    SKIP_CHANNELS_WITHOUT_COMMENTS, REQUEST_DELAY
)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Channel(BaseModel):
    """Модель Telegram канала"""
    name: str = Field(description="Название канала")
    username: str = Field(description="Юзернейм канала")
    subscribers_count: int = Field(description="Количество подписчиков")
    avg_post_reach: Optional[str] = Field(None, description="Средний охват поста")
    citation_index: Optional[str] = Field(None, description="Индекс цитирования")
    category: Optional[str] = Field(None, description="Категория канала")
    avatar_url: Optional[str] = Field(None, description="URL аватара канала")
    is_verified: bool = Field(False, description="Верифицирован ли канал")
    has_comments: Optional[bool] = Field(None, description="Открыты ли комментарии в канале")


class SearchResponse(BaseModel):
    """Базовая модель ответа от API поиска каналов"""
    status: str
    has_more: bool = Field(alias="hasMore")
    html: str


class SuccessResponse(SearchResponse):
    """Модель успешного ответа с результатами поиска"""
    channels: List[Channel] = Field(default_factory=list)
    
    def __init__(self, **data):
        super().__init__(**data)
        self.parse_html()
    
    def parse_html(self):
        """Парсинг HTML для извлечения информации о каналах"""
        soup = BeautifulSoup(self.html, 'html.parser')
        channel_cards = soup.find_all('div', class_='card-body py-2 position-relative')
        
        for card in channel_cards:
            try:
                # Извлекаем имя канала
                name_element = card.find('div', class_='text-truncate font-16 text-dark mt-n1')
                name = name_element.text.strip() if name_element else "Неизвестно"
                
                # Извлекаем юзернейм из ссылки
                link_element = card.find('a', href=re.compile(r'/channel/[@\w]+/stat'))
                username = "unknown"
                if link_element and 'href' in link_element.attrs:
                    match = re.search(r'/channel/([@\w]+)/stat', link_element['href'])
                    if match:
                        username = match.group(1)
                
                # Извлекаем количество подписчиков
                subscribers_element = card.find('div', class_='col col-4 pt-1').find('h4')
                subscribers_count = 0
                if subscribers_element:
                    subscribers_text = subscribers_element.text.strip().replace(' ', '')
                    subscribers_count = int(subscribers_text)
                
                # Извлекаем охват поста
                reach_elements = card.find_all('div', class_='col col-4 pt-1')
                avg_post_reach = None
                if len(reach_elements) > 1:
                    reach_element = reach_elements[1].find('h4')
                    if reach_element:
                        avg_post_reach = reach_element.text.strip()
                
                # Извлекаем индекс цитирования
                citation_index = None
                if len(reach_elements) > 2:
                    citation_element = reach_elements[2].find('h4')
                    if citation_element:
                        citation_index = citation_element.text.strip()
                
                # Извлекаем категорию
                category_element = card.find('span', class_='border rounded bg-light px-1')
                category = category_element.text.strip() if category_element else None
                
                # Извлекаем URL аватара
                avatar_element = card.find('img', class_=re.compile(r'img-thumbnail'))
                avatar_url = None
                if avatar_element and 'src' in avatar_element.attrs:
                    avatar_url = avatar_element['src']
                    if avatar_url.startswith('//'):
                        avatar_url = 'https:' + avatar_url
                
                # Проверяем верификацию канала
                is_verified = bool(card.find('img', class_=re.compile(r'border-success')))
                
                # Создаем объект Channel и добавляем в список
                channel = Channel(
                    name=name,
                    username=username,
                    subscribers_count=subscribers_count,
                    avg_post_reach=avg_post_reach,
                    citation_index=citation_index,
                    category=category,
                    avatar_url=avatar_url,
                    is_verified=is_verified
                )
                self.channels.append(channel)
            except Exception as e:
                # В случае ошибки при парсинге отдельного канала, продолжаем с следующим
                print(f"Ошибка при парсинге канала: {e}")
                continue


class ErrorResponse(SearchResponse):
    """Модель ответа при отсутствии результатов"""
    error_message: str = Field(default="Каналы не найдены")
    
    def __init__(self, **data):
        super().__init__(**data)
        self.parse_error_message()
    
    def parse_error_message(self):
        """Извлечение сообщения об ошибке из HTML"""
        soup = BeautifulSoup(self.html, 'html.parser')
        error_element = soup.find('p', class_='lead')
        if error_element:
            self.error_message = error_element.text.strip()


def parse_response(data: Dict[str, Any]) -> SearchResponse:
    """
    Функция для парсинга ответа API и создания соответствующего объекта
    
    Args:
        data: JSON-данные ответа API
        
    Returns:
        SearchResponse: объект SuccessResponse или ErrorResponse
    """
    response = SearchResponse(**data)
    
    # Проверяем, содержит ли HTML сообщение об ошибке
    if "No channel found" in response.html:
        return ErrorResponse(**data)
    else:
        return SuccessResponse(**data)


def build_payload(
    view: str = "",
    sort: str = "",
    q: str = "",
    inAbout: bool = False,
    categories: str = "",
    countries: str = "",
    languages: str = "",
    age: list[str] = [],
    err: list[str] = [],
    engagement_rate: int = 0,
    channelType: str = "public",
    male: int = 0,
    female: int = 0,
    participantsCountFrom: int = 1,
    participantsCountTo: int = 1_000_000_000,
    avgReachFrom: int = 0,
    avgReachTo: int = 1_000_000_000,
    avgReach24From: int = 0,
    avgReach24To: int = 1_000_000_000,
    ciFrom: int = 0,
    ciTo: int = 1_000_000_000,
    isVerified: bool = False,
    isRknVerified: bool = False,
    isStoriesAvailable: bool = False,
    noRedLabel: bool = False,
    noScam: bool = False,
    noDead: bool = False,
    page: int = 0,
    offset: int = 0,
):
    if view == "":
        view = "list"
    if sort == "":
        sort = "participants"
    if q == "":
        q = ""
    if inAbout == False:
        inAbout = "0"
    if inAbout == True:
        inAbout = "1"
    if categories == "":
        categories = ""
    if countries == "":
        countries = ""
    if age == []:
        age = [0, 120]
    if err == []:
        err = [0, 100]
    if isVerified == False:
        isVerified = "0"
    if isVerified == True:
        isVerified = "1"
    if isRknVerified == False:
        isRknVerified = "0"
    if isRknVerified == True:
        isRknVerified = "1"
    if isStoriesAvailable == False:
        isStoriesAvailable = "0"
    if isStoriesAvailable == True:
        isStoriesAvailable = "1"
    if noRedLabel == False:
        noRedLabel = "0"
    if noRedLabel == True:
        noRedLabel = "1"
    if noScam == False:
        noScam = "0"
    if noScam == True:
        noScam = "1"
    if noDead == False:
        noDead = "0"
    if noDead == True:
        noDead = "1"
    age = '-'.join(map(str, age))
    err = '-'.join(map(str, err))
    
    return f'_tgstat_csrk=lAS3AuR5Gtto6yhmkrcy6FPbl3c1zCk-EAS9icI42XTWZ-REgC19mByFYlbE_gKGNYnZAl2Gem4kY-rniBXqMQ%3D%3D&\
        view={view}&\
        sort={sort}&\
        q={q}&\
        inAbout={inAbout}&\
        categories={categories}&\
        countries={countries}&\
        languages={languages}&\
        channelType={channelType}&\
        age={age}&\
        err={err}&\
        er={engagement_rate}&\
        male={male}&\
        female={female}&\
        participantsCountFrom={participantsCountFrom}&\
        participantsCountTo={participantsCountTo}&\
        avgReachFrom={avgReachFrom}&\
        avgReachTo={avgReachTo}&\
        avgReach24From={avgReach24From}&\
        avgReach24To={avgReach24To}&\
        ciFrom={ciFrom}&\
        ciTo={ciTo}&\
        isVerified={isVerified}&\
        isRknVerified={isRknVerified}&\
        isStoriesAvailable={isStoriesAvailable}&\
        noRedLabel={noRedLabel}&\
        noScam={noScam}&\
        noDead={noDead}&\
        page={page}&\
        offset={offset}'


def save_channels_to_file(channels: List[Channel], filename: str = "channels.json"):
    """
    Сохранение списка каналов в JSON-файл
    
    Args:
        channels: Список объектов Channel
        filename: Имя файла для сохранения
    """
    # Преобразуем объекты Channel в словари
    channels_data = [channel.model_dump() for channel in channels]
    
    # Сохраняем в файл
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(channels_data, f, ensure_ascii=False, indent=4)
    
    print(f"Данные сохранены в файл {filename}")


def save_usernames_to_txt(channels: List[Channel], filename: str = "channels_usernames.txt"):
    """
    Сохранение юзернеймов каналов в TXT-файл в формате @username [комментарии: да/нет]
    
    Args:
        channels: Список объектов Channel
        filename: Имя файла для сохранения
    """
    with open(filename, 'w', encoding='utf-8') as f:
        for channel in channels:
            # Добавляем @ к юзернейму, если его нет
            username = channel.username
            if username and username != "unknown":
                if not username.startswith('@'):
                    username = f"@{username}"

                f.write(f"{username}\n")
    
    print(f"Юзернеймы каналов сохранены в файл {filename}")


def load_config(config_file: str = "search_config.json") -> Dict:
    """
    Загрузка конфигурации поиска из JSON-файла
    
    Args:
        config_file: Путь к файлу конфигурации
        
    Returns:
        Словарь с параметрами поиска
    """
    # Проверяем, существует ли файл конфигурации
    if not os.path.exists(config_file):
        # Если файла нет, создаем его с параметрами по умолчанию
        default_config = {
            "desc_query": "Список поисковых запросов для поиска каналов (обрабатываются последовательно)",
            "query": ["Crypto", "Finance", "Blockchain"],
            
            "desc_start_offset": "Начальное смещение для пагинации (с какой позиции начинать поиск)",
            "start_offset": 0,
            
            "desc_offset_step": "Шаг смещения для пагинации (обычно равен количеству результатов на странице)",
            "offset_step": 30,
            
            "desc_max_pages": "Максимальное количество страниц для обработки (null - без ограничений)",
            "max_pages": 10,
            
            "desc_delay_seconds": "Задержка между запросами в секундах (чтобы не перегружать сервер)",
            "delay_seconds": 1.5,
            
            "desc_categories": "Фильтр по категориям каналов (пустая строка - все категории)",
            "categories": "",
            
            "desc_countries": "Фильтр по странам (пустая строка - все страны)",
            "countries": "",
            
            "desc_languages": "Фильтр по языкам (пустая строка - все языки)",
            "languages": "",
            
            "desc_subscribers_min": "Минимальное количество подписчиков для фильтрации",
            "subscribers_min": 1000,
            
            "desc_subscribers_max": "Максимальное количество подписчиков для фильтрации",
            "subscribers_max": 10000000,
            
            "desc_is_verified": "Фильтр по верифицированным каналам (true - только верифицированные)",
            "is_verified": False,
            
            "desc_output_json": "Имя JSON-файла для сохранения полной информации о каналах (можно использовать {query} для подстановки)",
            "output_json": "{query}_channels.json",
            
            "desc_output_txt": "Имя TXT-файла для сохранения списка юзернеймов каналов (можно использовать {query} для подстановки)",
            "output_txt": "{query}_usernames.txt"
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=4)
            
        print(f"Создан файл конфигурации {config_file} с параметрами по умолчанию")
        return {k: v for k, v in default_config.items() if not k.startswith('desc_')}
    
    # Загружаем конфигурацию из файла
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    print(f"Загружена конфигурация из файла {config_file}")
    
    # Удаляем описания из конфигурации
    filtered_config = {k: v for k, v in config.items() if not k.startswith('desc_')}
    
    return filtered_config


def search_all_pages(
    query: str = "Auto",
    start_offset: int = 30,
    verbose: bool = True,
    **additional_params
) -> List[Channel]:
    """
    Args:
        query: поисковый запрос
        start_offset: начальное смещение для поиска
        offset_step: размер шага для смещения (обычно равен количеству результатов на странице)
        max_pages: игнорируется, функция всегда обрабатывает только первую страницу
        delay_seconds: задержка между запросами в секундах (не используется)
        verbose: выводить ли информацию о процессе поиска
        additional_params: дополнительные параметры для build_payload
        
    Returns:
        Список объектов Channel с первой страницы
    """
    url = "https://tgstat.com/channels/search"
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Accept': '*/*',
        'Sec-Fetch-Site': 'same-origin',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Sec-Fetch-Mode': 'cors',
        'Origin': 'https://tgstat.com',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3.1 Safari/605.1.15',
        'Referer': 'https://tgstat.com/channels/search',
        'X-Requested-With': 'XMLHttpRequest',
    }
    
    # Обработка дополнительных параметров
    payload_params = {
        'q': query,
        'offset': start_offset
    }
    
    # Добавляем параметры для фильтрации по количеству подписчиков, если они указаны
    if 'subscribers_min' in additional_params:
        payload_params['participantsCountFrom'] = additional_params['subscribers_min']
    if 'subscribers_max' in additional_params:
        payload_params['participantsCountTo'] = additional_params['subscribers_max']
    
    # Добавляем категории и страны, если они указаны
    if 'categories' in additional_params and additional_params['categories']:
        payload_params['categories'] = additional_params['categories']
    if 'countries' in additional_params and additional_params['countries']:
        payload_params['countries'] = additional_params['countries']
    if 'languages' in additional_params and additional_params['languages']:
        payload_params['languages'] = additional_params['languages']
    
    # Добавляем другие фильтры
    if 'is_verified' in additional_params:
        payload_params['isVerified'] = additional_params['is_verified']
    
    # Список для хранения найденных каналов
    all_channels = []
    
    # Текущее смещение
    current_offset = start_offset
    
    # Создаем параметры запроса
    payload = build_payload(**payload_params)
    
    try:
        # Выполняем запрос
        response = requests.post(url, data=payload, headers=headers)
        response.raise_for_status()
        
        # Парсим ответ
        data = response.json()
        parsed_response = parse_response(data)
        
        # Обрабатываем результаты
        if isinstance(parsed_response, SuccessResponse):
            all_channels.extend(parsed_response.channels)
            
            if len(parsed_response.channels) > 0 and verbose:
                print(f"  Последний канал в выборке: {parsed_response.channels[-1].name}")
        else:
            # Если ответ содержит ошибку или нет результатов
            if verbose:
                if isinstance(parsed_response, ErrorResponse):
                    print(f"  Ошибка: {parsed_response.error_message}")
                else:
                    print("  Неизвестный формат ответа")
            
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"Ошибка при выполнении запроса: {e}")
    except Exception as e:
        if verbose:
            print(f"Неожиданная ошибка: {e}")
    
    return all_channels


async def check_channel_comments(client, channel_username: str, delay: float = REQUEST_DELAY) -> bool:
    """
    Проверяет, включены ли комментарии в телеграм канале
    
    Args:
        client: экземпляр TelegramClient 
        channel_username: юзернейм канала (с @ или без)
        delay: задержка перед выполнением запроса (предотвращает флуд)
    
    Returns:
        bool: True если комментарии открыты, False если закрыты, None в случае ошибки
    """
    # Добавляем задержку для предотвращения флуда API
    await asyncio.sleep(delay)
    
    # Убеждаемся, что юзернейм не начинается с @
    if channel_username.startswith('@'):
        channel_username = channel_username[1:]
    
    # Если юзернейм пустой или unknown, возвращаем None
    if not channel_username or channel_username == "unknown":
        logger.warning(f"Пропуск проверки: невалидный юзернейм '{channel_username}'")
        return None
    
    try:
        logger.info(f"Проверка комментариев для канала @{channel_username}")
        
        # Получаем сущность канала
        channel_entity = await client.get_entity(f"@{channel_username}")
        
        # Получаем полную информацию о канале
        full_channel = await client(GetFullChannelRequest(channel=channel_entity))
        
        # Проверяем наличие linked_chat_id
        has_comments = full_channel.full_chat.linked_chat_id is not None
        
        logger.info(f"Канал @{channel_username} {'имеет' if has_comments else 'не имеет'} открытые комментарии")
        return has_comments
    
    except Exception as e:
        return None


async def check_channels_comments(channels: List[Channel], config: Dict) -> List[Channel]:
    """
    Проверяет наличие открытых комментариев для списка каналов
    
    Args:
        channels: список объектов Channel для проверки
        config: конфигурация с параметрами поиска
    
    Returns:
        List[Channel]: список каналов с заполненным полем has_comments, 
        при SKIP_CHANNELS_WITHOUT_COMMENTS=True возвращаются только каналы с открытыми комментариями
    """
    # Проверяем, включена ли проверка комментариев
    if not CHECK_COMMENTS:
        logger.info("Проверка комментариев отключена в конфигурации")
        return channels
    
    # Проверяем наличие API-ключей
    if not API_ID or not API_HASH:
        logger.error("API ID или API Hash для Telegram не указаны в конфигурации telethon_settings.json")
        return channels
    
    # Создаем клиент Telethon
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    try:
        # Запускаем клиент
        await client.start()
        logger.info("Telethon клиент запущен успешно")
        
        # Список для хранения результатов
        checked_channels = []
        
        # Всего каналов для проверки
        total_channels = len(channels)
        
        # Проверяем каждый канал
        for i, channel in enumerate(channels):
            logger.info(f"Обработка канала {i+1}/{total_channels}: {channel.username}")
            
            # Проверяем наличие комментариев
            has_comments = await check_channel_comments(client, channel.username, REQUEST_DELAY)
            
            # Обновляем поле has_comments
            channel.has_comments = has_comments
            
            # Добавляем канал в результаты, если не пропускаем каналы без комментариев
            # или если у канала есть комментарии
            if not SKIP_CHANNELS_WITHOUT_COMMENTS or has_comments:
                checked_channels.append(channel)
        
        logger.info(f"Проверка комментариев завершена. Всего каналов: {total_channels}, "
                   f"после фильтрации: {len(checked_channels)}")
        
        return checked_channels
        
    finally:
        # Закрываем клиент
        await client.disconnect()
        logger.info("Telethon клиент отключен")


def main():
    """Запуск поиска с конфигурацией из JSON-файла"""
    
    # Загружаем конфигурацию из файла
    config = load_config()
    
    # Проверяем, является ли query списком
    queries = config['query']
    if not isinstance(queries, list):
        queries = [queries]  # Если не список, преобразуем в список из одного элемента
    
    # Создаем директорию output, если она не существует
    output_dir = "./output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Создана директория {output_dir}")
    
    # Генерируем уникальное имя файла на основе текущей даты и времени
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_json_file = os.path.join(output_dir, f"channels_{timestamp}.json")
    output_txt_file = os.path.join(output_dir, f"usernames_{timestamp}.txt")
    
    # Список для хранения всех найденных каналов
    all_channels = []
    
    # Словарь для статистики
    channels_by_query = {}
    
    # Обрабатываем каждый запрос последовательно
    for query in queries:
        print(f"\n{'='*50}")
        print(f"Поиск по запросу: {query}")
        print(f"{'='*50}")
        
        # Создаем базовые параметры поиска из конфигурации
        search_params = {
            'query': query,
            'start_offset': config['start_offset'],
            'verbose': True
        }
        
        # Добавляем дополнительные параметры, если они есть в конфигурации
        for param in ['categories', 'countries', 'languages', 
                     'subscribers_min', 'subscribers_max', 'is_verified']:
            if param in config:
                search_params[param] = config[param]
        
        # Выполняем поиск для текущего запроса
        channels = search_all_pages(**search_params)
        
        # Сохраняем найденные каналы в общий список
        all_channels.extend(channels)
        
        # Сохраняем статистику по текущему запросу
        channels_by_query[query] = len(channels)
        
        print(f"Обработка запроса '{query}' завершена. Найдено каналов: {len(channels)}")
    
    # Проверяем наличие открытых комментариев, если это требуется
    if CHECK_COMMENTS:
        print("\n" + "="*50)
        print("ПРОВЕРКА ОТКРЫТЫХ КОММЕНТАРИЕВ")
        print("="*50)
        
        # Запускаем асинхронную функцию проверки комментариев
        all_channels = asyncio.run(check_channels_comments(all_channels, config))
        
        if SKIP_CHANNELS_WITHOUT_COMMENTS:
            print(f"Каналы без комментариев пропущены. Осталось каналов: {len(all_channels)}")
    
    # Сохраняем все каналы в один JSON-файл
    save_channels_to_file(all_channels, output_json_file)
    
    # Сохраняем все юзернеймы в один TXT-файл
    save_usernames_to_txt(all_channels, output_txt_file)
    
    # Выводим общую статистику по всем запросам
    print("\n" + "="*50)
    print("ОБЩАЯ СТАТИСТИКА")
    print("="*50)
    
    print(f"Всего обработано запросов: {len(queries)}")
    print(f"Общее количество найденных каналов: {len(all_channels)}")
    print(f"Результаты сохранены в файлы: {output_json_file} и {output_txt_file}")


if __name__ == "__main__":
    main() 