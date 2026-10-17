from typing import Any

from .base import EditIntent, IntentCompiler


class IntentCompilerRegistry:
    """Maps a concrete intent type to the compiler that is responsible for it."""

    def __init__(self) -> None:
        self._compilers: dict[type[EditIntent], IntentCompiler[Any]] = {}

    def register[I: EditIntent](
        self,
        *,
        intent_type: type[I],
        compiler: IntentCompiler[I],
    ) -> None:
        self._compilers[intent_type] = compiler

    def get[I: EditIntent](self, *, intent_type: type[I]) -> IntentCompiler[I]:
        return self._compilers[intent_type]
