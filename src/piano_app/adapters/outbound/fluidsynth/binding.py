"""Small typed boundary around the native FluidSynth API; no audio device is opened."""

import ctypes as c
import os
import sys
from array import array
from ctypes.util import find_library
from pathlib import Path

from .errors import FluidSynthError


class FluidSynthSession:
    def __init__(
        self,
        *,
        soundfont: Path,
        sample_rate: int,
        channels: int,
        gain: float,
        library_path: str | None = None,
    ) -> None:
        if not soundfont.is_file():
            raise FluidSynthError(f"SoundFont does not exist: {soundfont}")
        library = library_path or find_library("fluidsynth")
        if library is None:
            raise FluidSynthError("FluidSynth library was not found; configure library_path.")
        try:
            self._lib = c.CDLL(library)
            self._configure_api()
        except (OSError, AttributeError) as error:
            raise FluidSynthError(f"Cannot load FluidSynth: {error}") from error
        self._settings: int | None = None
        self._synth: int | None = None
        self._prepared: set[int] = set()
        try:
            self._settings = self._lib.new_fluid_settings()
            if not self._settings:
                raise FluidSynthError("Cannot allocate FluidSynth settings.")
            self._check(
                self._lib.fluid_settings_setnum(self._settings, b"synth.sample-rate", sample_rate)
            )
            self._check(self._lib.fluid_settings_setnum(self._settings, b"synth.gain", gain))
            self._check(
                self._lib.fluid_settings_setint(self._settings, b"synth.midi-channels", channels)
            )
            self._synth = self._lib.new_fluid_synth(self._settings)
            if not self._synth:
                raise FluidSynthError("Cannot allocate FluidSynth synthesizer.")
            self._soundfont_id: int = self._lib.fluid_synth_sfload(
                self._synth, os.fsencode(soundfont), 0
            )
            self._check(self._soundfont_id)
        except BaseException:
            self.close()
            raise

    def note_on(self, *, channel: int, pitch: int, velocity: int) -> None:
        synth = self._open_synth()
        if channel not in self._prepared:
            self._check(self._lib.fluid_synth_set_channel_type(synth, channel, 0))
            self._check(
                self._lib.fluid_synth_program_select(synth, channel, self._soundfont_id, 0, 0)
            )
            self._prepared.add(channel)
        self._check(self._lib.fluid_synth_noteon(synth, channel, pitch, velocity))

    def note_off(self, *, channel: int, pitch: int) -> None:
        self._check(self._lib.fluid_synth_noteoff(self._open_synth(), channel, pitch))

    def read(self, *, frames: int) -> bytes:
        if frames < 1:
            raise FluidSynthError("Audio reads require positive frame counts.")
        output = (c.c_int16 * (frames * 2))()
        self._check(
            self._lib.fluid_synth_write_s16(
                self._open_synth(),
                frames,
                output,
                0,
                2,
                output,
                1,
                2,
            )
        )
        pcm = bytes(output)
        if sys.byteorder != "little":
            samples = array("h")
            samples.frombytes(pcm)
            samples.byteswap()
            pcm = samples.tobytes()
        return pcm

    def close(self) -> None:
        synth, self._synth = self._synth, None
        settings, self._settings = self._settings, None
        try:
            if synth:
                self._lib.delete_fluid_synth(synth)
        finally:
            if settings:
                self._lib.delete_fluid_settings(settings)

    def _open_synth(self) -> int:
        if not self._synth:
            raise FluidSynthError("Synthesizer session is closed.")
        return self._synth

    @staticmethod
    def _check(result: int) -> None:
        if result < 0:
            raise FluidSynthError("FluidSynth operation failed.")

    def _configure_api(self) -> None:
        signatures: dict[str, tuple[object, list[object]]] = {
            "new_fluid_settings": (c.c_void_p, []),
            "delete_fluid_settings": (None, [c.c_void_p]),
            "fluid_settings_setnum": (c.c_int, [c.c_void_p, c.c_char_p, c.c_double]),
            "fluid_settings_setint": (c.c_int, [c.c_void_p, c.c_char_p, c.c_int]),
            "new_fluid_synth": (c.c_void_p, [c.c_void_p]),
            "delete_fluid_synth": (None, [c.c_void_p]),
            "fluid_synth_sfload": (c.c_int, [c.c_void_p, c.c_char_p, c.c_int]),
            "fluid_synth_set_channel_type": (c.c_int, [c.c_void_p, c.c_int, c.c_int]),
            "fluid_synth_program_select": (c.c_int, [c.c_void_p] + [c.c_int] * 4),
            "fluid_synth_noteon": (c.c_int, [c.c_void_p] + [c.c_int] * 3),
            "fluid_synth_noteoff": (c.c_int, [c.c_void_p] + [c.c_int] * 2),
            "fluid_synth_write_s16": (
                c.c_int,
                [c.c_void_p, c.c_int, c.c_void_p, c.c_int, c.c_int, c.c_void_p, c.c_int, c.c_int],
            ),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self._lib, name)
            function.restype = result
            function.argtypes = arguments
