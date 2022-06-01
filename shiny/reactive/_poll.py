import functools
import os
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    TypeVar,
    Union,
    cast,
)

import shiny
import _utils
from shiny.types import MISSING, MISSING_TYPE
from shiny import reactive
from .._docstring import add_example

if TYPE_CHECKING:
    from ..session import Session

__all__ = ["poll", "file_reader"]

T = TypeVar("T")


def poll(
    poll_func: Callable[[], Any],
    interval_secs: float = 1,
    *,
    priority: int = 0,
    compare: Optional[Callable[[Any, Any], bool]] = None,
    session: Union[MISSING_TYPE, "Session", None] = MISSING,
) -> Callable[[Callable[[], T]], Callable[[], T]]:

    if compare is None:
        compare = shiny.equal

    with reactive.isolate():
        last_value: reactive.Value[Any] = reactive.Value(poll_func())

    @reactive.Effect(priority=priority, session=session)
    async def _():
        try:
            if _utils.is_async_callable(poll_func):
                new = await poll_func()
            else:
                new = poll_func()

            with reactive.isolate():
                old = last_value.get()
            if not compare(old, new):
                last_value.set(new)
        finally:
            reactive.invalidate_later(interval_secs)

    def wrapper(fn: Callable[[], T]) -> Callable[[], T]:
        if _utils.is_async_callable(fn):

            @reactive.Calc(session=session)
            @functools.wraps(fn)
            async def result_async() -> T:
                last_value.get()
                return await fn()

            return cast(Callable[[], T], result_async)

        else:

            @reactive.Calc(session=session)
            @functools.wraps(fn)
            def result_sync() -> T:
                # Take dependency on polling result
                last_value.get()

                # Note that we also depend on the main function
                return fn()

            return result_sync

    return wrapper


@add_example()
def file_reader(
    filepath: Union[str, Callable[[], str]],
    interval_secs: float = 1,
    *,
    priority: int = 1,
    session: Union[MISSING_TYPE, "Session", None] = MISSING,
) -> Callable[[Callable[[], T]], Callable[[], T]]:
    if isinstance(filepath, str):
        # Normalize filepath so it's always a function

        filepath_value = filepath

        def filepath_func() -> str:
            return filepath_value

        filepath = filepath_func

    def check_timestamp():
        path = filepath()
        return (path, os.path.getmtime(path), os.path.getsize(path))

    def wrapper(fn: Callable[[], T]) -> Callable[[], T]:
        if _utils.is_async_callable(fn):

            @poll(
                check_timestamp,
                interval_secs=interval_secs,
                priority=priority,
                session=session,
            )
            @functools.wraps(fn)
            async def reader_async():
                return await fn()

            return cast(Callable[[], T], reader_async)
        else:

            @poll(
                check_timestamp,
                interval_secs=interval_secs,
                priority=priority,
                session=session,
            )
            @functools.wraps(fn)
            def reader():
                return fn()

            return reader

    return wrapper
