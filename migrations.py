"""Миграции базы данных"""
import logging
from database import db

logger = logging.getLogger(__name__)

async def create_tables():
    """Создание всех таблиц базы данных"""
    
    # Таблица пользователей
    await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username VARCHAR(255),
            full_name VARCHAR(255),
            is_admin BOOLEAN DEFAULT FALSE,
            is_master BOOLEAN DEFAULT FALSE,
            timezone VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица услуг
    await db.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            price DECIMAL(10, 2) NOT NULL,
            duration_minutes INTEGER NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            is_additional BOOLEAN DEFAULT FALSE,
            order_index INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Добавляем поле is_additional если его нет
    try:
        await db.execute("""
            ALTER TABLE services ADD COLUMN IF NOT EXISTS is_additional BOOLEAN DEFAULT FALSE
        """)
    except:
        pass
    
    # Таблица расписания
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            start_time TIME,
            end_time TIME,
            is_day_off BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date)
        )
    """)
    
    # Таблица записей
    await db.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES users(id),
            service_id INTEGER NOT NULL REFERENCES services(id),
            appointment_date TIMESTAMP NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            total_price DECIMAL(10, 2) DEFAULT 0,
            total_duration INTEGER DEFAULT 0,
            admin_comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Добавляем колонку admin_comment если она еще не существует (для существующих БД)
    try:
        await db.execute("""
            ALTER TABLE appointments 
            ADD COLUMN IF NOT EXISTS admin_comment TEXT
        """)
    except Exception as e:
        # Колонка уже существует или другая ошибка - игнорируем
        pass
    
    # Таблица клиентов (расширенная информация)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
            phone VARCHAR(20),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица тегов клиентов
    await db.execute("""
        CREATE TABLE IF NOT EXISTS client_tags (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            tag VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица заметок о клиентах
    await db.execute("""
        CREATE TABLE IF NOT EXISTS client_notes (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            note TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица черного списка
    await db.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица истории записей
    await db.execute("""
        CREATE TABLE IF NOT EXISTS appointments_history (
            id SERIAL PRIMARY KEY,
            appointment_id INTEGER NOT NULL REFERENCES appointments(id),
            old_status VARCHAR(50),
            new_status VARCHAR(50),
            changed_by INTEGER REFERENCES users(id),
            change_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица настроек бота (кастомизация)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            id SERIAL PRIMARY KEY,
            key VARCHAR(255) UNIQUE NOT NULL,
            value TEXT NOT NULL,
            type VARCHAR(50) DEFAULT 'text',
            is_hidden BOOLEAN DEFAULT FALSE,
            order_index INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица настроек подтверждения записей
    await db.execute("""
        CREATE TABLE IF NOT EXISTS appointment_settings (
            id SERIAL PRIMARY KEY,
            require_confirmation BOOLEAN DEFAULT FALSE,
            reminder_24h_enabled BOOLEAN DEFAULT TRUE,
            reminder_1_2h_enabled BOOLEAN DEFAULT TRUE,
            reminder_interval_hours INTEGER DEFAULT 2,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица информации (адрес, контакты, соцсети и т.д.)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS info_sections (
            id SERIAL PRIMARY KEY,
            key VARCHAR(100) UNIQUE NOT NULL,
            title VARCHAR(255) NOT NULL,
            content TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            order_index INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица FAQ
    await db.execute("""
        CREATE TABLE IF NOT EXISTS faq (
            id SERIAL PRIMARY KEY,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            order_index INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица напоминаний
    await db.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            appointment_id INTEGER NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
            reminder_type VARCHAR(50) NOT NULL,  -- 24h, 1-2h, follow_up
            scheduled_at TIMESTAMP NOT NULL,
            sent BOOLEAN DEFAULT FALSE,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Создаем индекс для быстрого поиска по дате расписания
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedule(date)
    """)
    
    # Создаем индекс для поиска записей по дате
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date)
    """)
    
    # Создаем индекс для поиска записей клиента
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_appointments_client ON appointments(client_id)
    """)
    
    # Вставляем начальные настройки подтверждения
    await db.execute("""
        INSERT INTO appointment_settings (id, require_confirmation, reminder_24h_enabled, reminder_1_2h_enabled, reminder_interval_hours)
        VALUES (1, FALSE, TRUE, TRUE, 2)
        ON CONFLICT DO NOTHING
    """)
    
    # Таблица дополнительных услуг для записей
    await db.execute("""
        CREATE TABLE IF NOT EXISTS appointment_additional_services (
            id SERIAL PRIMARY KEY,
            appointment_id INTEGER NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
            service_id INTEGER NOT NULL REFERENCES services(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица связей основных и дополнительных услуг
    # Если main_service_id IS NULL, то дополнительная услуга доступна для всех основных услуг
    await db.execute("""
        CREATE TABLE IF NOT EXISTS services_additional_links (
            id SERIAL PRIMARY KEY,
            additional_service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
            main_service_id INTEGER REFERENCES services(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(additional_service_id, main_service_id)
        )
    """)
    
    # Вставляем начальные разделы информации
    initial_info_sections = [
        ('address', 'Адрес', '', 1),
        ('map', 'Карта', '', 2),
        ('how_to_get', 'Как добраться', '', 3),
        ('contacts', 'Контакты', '', 4),
        ('social_media', 'Соцсети', '', 5),
        ('portfolio', 'Портфолио', '', 6),
        ('master_description', 'Описание мастера', '', 7),
        ('booking_rules', 'Правила записи', '', 8),
    ]
    
    for key, title, content, order_idx in initial_info_sections:
        await db.execute("""
            INSERT INTO info_sections (key, title, content, order_index)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (key) DO NOTHING
        """, key, title, content, order_idx)
    
    logger.info("Таблицы базы данных созданы")


