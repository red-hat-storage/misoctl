import os
import errno
from hashlib import md5


def ensure_directory(path):
    """
    Gracefully make a directory (and its parents), if it does not exist.
    """
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def get_md5sum(filename):
    """ Return the hex md5 digest for a file. """
    chsum = md5()
    with open(filename, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            chsum.update(chunk)
    digest = chsum.hexdigest()
    return digest
