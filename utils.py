import tarfile
import zipfile
from fnmatch import fnmatch
import os


def extract_archive(archive_path, extract_to):
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, 'r:*') as tar_ref:
            tar_ref.extractall(extract_to)
    else:
        raise Exception("Unsupported archive format")


def is_archive(file_path):
    return zipfile.is_zipfile(file_path) or tarfile.is_tarfile(file_path)

def normalise_path(path):
    return path.replace(os.sep, '/')


def match_pattern(path, pattern):
    normalised_path = normalise_path(path)
    normalised_pattern = normalise_path(pattern)

    if fnmatch(normalised_path, normalised_pattern):
        return True
    
    if normalised_pattern.startswith("**/"):
        return fnmatch(normalised_path, normalised_pattern[3:])
    
    return False
