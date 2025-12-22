"""Сервис для работы с пользователями"""
from typing import Optional
from database import db
from models import User

class UserService:
    """Сервис для работы с пользователями"""
    
    @staticmethod
    async def get_or_create_user(
        telegram_id: int,
        username: Optional[str] = None,
        full_name: Optional[str] = None
    ) -> User:
        """Получить или создать пользователя"""
        user = await db.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id
        )
        
        if user:
            return User(
                id=user['id'],
                telegram_id=user['telegram_id'],
                username=user['username'],
                full_name=user['full_name'],
                is_admin=user['is_admin'],
                is_master=user['is_master'],
                timezone=user['timezone'],
                created_at=user['created_at']
            )
        
        # Создаем нового пользователя
        user_id = await db.fetchval(
            """
            INSERT INTO users (telegram_id, username, full_name)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            telegram_id, username, full_name
        )
        
        return User(
            id=user_id,
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            is_admin=False,
            is_master=False,
            timezone=None,
            created_at=None
        )
    
    @staticmethod
    async def is_admin(telegram_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        result = await db.fetchval(
            "SELECT is_admin FROM users WHERE telegram_id = $1",
            telegram_id
        )
        return result or False
    
    @staticmethod
    async def is_master(telegram_id: int) -> bool:
        """Проверить, является ли пользователь мастером"""
        result = await db.fetchval(
            "SELECT is_master FROM users WHERE telegram_id = $1",
            telegram_id
        )
        return result or False
    
    @staticmethod
    async def set_timezone(telegram_id: int, timezone: str):
        """Установить часовой пояс пользователя"""
        await db.execute(
            "UPDATE users SET timezone = $1 WHERE telegram_id = $2",
            timezone, telegram_id
        )
    
    @staticmethod
    async def is_blacklisted(telegram_id: int) -> bool:
        """Проверить, находится ли пользователь в черном списке"""
        result = await db.fetchval(
            "SELECT id FROM blacklist WHERE user_id = (SELECT id FROM users WHERE telegram_id = $1)",
            telegram_id
        )
        return result is not None


