from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(services: Annotated[Services, Depends(get_services)]) -> AsyncIterator[AsyncSession]:
    async with services.session_factory() as session:
        yield session


ServicesDep = Annotated[Services, Depends(get_services)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
