import io
import os
import sys
import tarfile
import tempfile
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import extract_archive, is_archive
import app

def make_zip(files: dict) -> str:
    """Write a zip containing {filename: content} to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(tmp.name, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return tmp.name


def make_tar_gz(files: dict) -> str:
    """Write a .tar.gz containing {filename: content} to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
    with tarfile.open(tmp.name, "w:gz") as tf:
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return tmp.name


class TestExtractArchive:
    def test_extract_zip(self):
        path = make_zip({"hello.txt": "hello", "sub/world.txt": "world"})
        try:
            with tempfile.TemporaryDirectory() as dest:
                extract_archive(path, dest)
                assert os.path.exists(os.path.join(dest, "hello.txt"))
                assert os.path.exists(os.path.join(dest, "sub", "world.txt"))
        finally:
            os.unlink(path)

    def test_extract_tar_gz(self):
        path = make_tar_gz({"notes.txt": "some notes"})
        try:
            with tempfile.TemporaryDirectory() as dest:
                extract_archive(path, dest)
                assert os.path.exists(os.path.join(dest, "notes.txt"))
        finally:
            os.unlink(path)

    def test_unsupported_format_raises(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        tmp.write(b"not an archive")
        tmp.close()
        try:
            with tempfile.TemporaryDirectory() as dest:
                with pytest.raises(Exception, match="Unsupported archive format"):
                    extract_archive(tmp.name, dest)
        finally:
            os.unlink(tmp.name)

    def test_zip_contents_correct(self):
        path = make_zip({"data.txt": "file content"})
        try:
            with tempfile.TemporaryDirectory() as dest:
                extract_archive(path, dest)
                with open(os.path.join(dest, "data.txt")) as f:
                    assert f.read() == "file content"
        finally:
            os.unlink(path)
