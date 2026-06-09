import tarfile
import zipfile
from fnmatch import fnmatch


def extract_archive(archive_path, extract_to):
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, 'r') as tar_ref:
            tar_ref.extractall(extract_to)
    else:
        raise Exception("Unsupported archive format")


def is_archive(file_path):
    lower = file_path.lower()
    return (
        lower.endswith('.zip') or
        lower.endswith('.tar') or
        lower.endswith('.tar.gz') or
        lower.endswith('.tgz')
    )
