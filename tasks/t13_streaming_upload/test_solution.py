import asyncio
import tracemalloc

import pytest

from solution import UploadTooLarge, save_upload

CHUNK = 64 * 1024


class Stream:
    """Асинхронний потік з лічильником реально прочитаних шматків."""

    def __init__(self, total, chunk=CHUNK, fail_after=None, on_chunk=None):
        self.total, self.chunk, self.fail_after, self.on_chunk = total, chunk, fail_after, on_chunk
        self.yielded = 0

    async def __aiter__(self):
        sent = 0
        while sent < self.total:
            if self.fail_after is not None and self.yielded >= self.fail_after:
                raise ConnectionResetError("client went away")
            size = min(self.chunk, self.total - sent)
            if self.on_chunk:
                self.on_chunk(self.yielded)
            self.yielded += 1
            sent += size
            yield b"x" * size
            await asyncio.sleep(0)


def run(coro):
    return asyncio.run(coro)


def test_small_upload_is_saved(tmp_path):
    dest = tmp_path / "f.bin"
    assert run(save_upload(Stream(100_000), dest, max_bytes=1_000_000)) == 100_000
    assert dest.read_bytes() == b"x" * 100_000


def test_empty_upload_is_allowed(tmp_path):
    dest = tmp_path / "empty.bin"
    assert run(save_upload(Stream(0), dest, max_bytes=10)) == 0
    assert dest.read_bytes() == b""


def test_exactly_max_bytes_is_allowed(tmp_path):
    dest = tmp_path / "f.bin"
    assert run(save_upload(Stream(CHUNK * 3 + 5), dest, max_bytes=CHUNK * 3 + 5)) == CHUNK * 3 + 5


def test_memory_does_not_depend_on_file_size(tmp_path):
    dest = tmp_path / "big.bin"
    tracemalloc.start()
    try:
        written = run(save_upload(Stream(40 * 1024 * 1024), dest, max_bytes=100 * 1024 * 1024))
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert written == 40 * 1024 * 1024
    assert dest.stat().st_size == written
    assert peak < 2 * 1024 * 1024, f"пік пам'яті {peak // 1024} КБ для файлу 40 МБ: файл читається в пам'ять"


def test_limit_stops_reading_early_and_leaves_nothing(tmp_path):
    dest = tmp_path / "f.bin"
    stream = Stream(50 * 1024 * 1024)
    with pytest.raises(UploadTooLarge):
        run(save_upload(stream, dest, max_bytes=CHUNK * 4))
    assert stream.yielded <= 6, f"споживано {stream.yielded} шматків: після перевищення ліміту читання має зупинитись"
    assert list(tmp_path.iterdir()) == []


def test_destination_appears_only_after_full_upload(tmp_path):
    dest = tmp_path / "f.bin"
    seen = []
    stream = Stream(CHUNK * 5, on_chunk=lambda i: seen.append(dest.exists()))
    run(save_upload(stream, dest, max_bytes=10**9))
    assert seen == [False] * 5, "dest не має існувати, поки завантаження не завершилось"
    assert dest.exists()


def test_connection_drop_leaves_no_partial_files_and_propagates(tmp_path):
    dest = tmp_path / "f.bin"
    with pytest.raises(ConnectionResetError):
        run(save_upload(Stream(CHUNK * 10, fail_after=3), dest, max_bytes=10**9))
    assert list(tmp_path.iterdir()) == []


def test_existing_file_survives_failed_upload(tmp_path):
    dest = tmp_path / "f.bin"
    dest.write_bytes(b"old")
    with pytest.raises(UploadTooLarge):
        run(save_upload(Stream(CHUNK * 10), dest, max_bytes=CHUNK))
    assert dest.read_bytes() == b"old"
