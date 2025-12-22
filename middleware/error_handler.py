"""Middleware для обработки ошибок и отправки их администратору"""
import logging
import traceback
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from aiogram import Bot
from config import LOG_ADMIN_ID

logger = logging.getLogger(__name__)

class ErrorHandlerMiddleware(BaseMiddleware):
    """Middleware для перехвата и обработки всех ошибок"""
    
    def __init__(self, bot: Bot):
        super().__init__()
        self.bot = bot
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            # Логируем ошибку
            logger.exception(f"Ошибка в обработчике: {e}")
            
            # Формируем сообщение с трассировкой стека
            error_message = self._format_error_message(e, event)
            
            # Отправляем администратору
            try:
                await self.bot.send_message(
                    LOG_ADMIN_ID,
                    error_message,
                    parse_mode='HTML'
                )
            except Exception as send_error:
                logger.error(f"Не удалось отправить сообщение об ошибке: {send_error}")
            
            # Пробрасываем ошибку дальше
            raise
    
    def _format_error_message(self, error: Exception, event: TelegramObject) -> str:
        """Форматировать сообщение об ошибке с трассировкой стека"""
        error_type = type(error).__name__
        error_text = str(error)
        traceback_text = traceback.format_exc()
        
        # Получаем информацию о событии
        event_info = self._get_event_info(event)
        
        message = (
            f"<b>⚠️ Ошибка в боте</b>\n\n"
            f"<b>Тип ошибки:</b> {error_type}\n"
            f"<b>Сообщение:</b> {error_text}\n\n"
            f"<b>Информация о событии:</b>\n{event_info}\n\n"
            f"<b>Трассировка стека:</b>\n"
            f"<code>{traceback_text}</code>"
        )
        
        # Ограничиваем длину сообщения (Telegram имеет лимит 4096 символов)
        if len(message) > 4000:
            message = message[:3900] + "\n\n... (сообщение обрезано)"
        
        return message
    
    def _get_event_info(self, event: TelegramObject) -> str:
        """Получить информацию о событии"""
        if isinstance(event, Update):
            if event.message:
                return (
                    f"Type: Message\n"
                    f"Chat ID: {event.message.chat.id}\n"
                    f"User ID: {event.message.from_user.id if event.message.from_user else 'N/A'}\n"
                    f"Text: {event.message.text[:100] if event.message.text else 'N/A'}"
                )
            elif event.callback_query:
                return (
                    f"Type: CallbackQuery\n"
                    f"User ID: {event.callback_query.from_user.id}\n"
                    f"Data: {event.callback_query.data[:100] if event.callback_query.data else 'N/A'}"
                )
        return f"Type: {type(event).__name__}"






