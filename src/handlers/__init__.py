from aiogram import Dispatcher
from . import aider, documents, common

def register_all_handlers(dp: Dispatcher):
    dp.include_router(aider.router)
    dp.include_router(documents.router)
    dp.include_router(common.router)