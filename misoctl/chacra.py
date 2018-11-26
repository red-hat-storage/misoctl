import os
from hashlib import sha512
import posixpath
from misoctl.log import log as log
from misoctl.util import ensure_directory

"""
Methods for interacting with builds in Chacra.
"""


def name_version(nvr):
    """
    Split a Debian NVR into "name" and "version".

    :raises RuntimeError if this does not look like a valid package.
    """
    try:
        return nvr.split('_', 1)
    except ValueError:
        # Friendlier error message here:
        err = '%s is not a valid package build N-V-R' % nvr
        raise RuntimeError(err)


def name_version_release(nvr):
    # Nothing mandates that all Debian packages must have a "-" in the Version
    # field to split into Koji's concepts of "version" and "release". If we
    # come across this pattern in a package, arbitrarily set the "release"
    # value to "0" to satisfy Koji.
    # (In Debian terminology, the names are "upstream version", and "debian
    # revision")
    (name, version) = name_version(nvr)
    try:
        version, release = version.split('-', 1)
    except ValueError:
        release = '0'
    return (name, version, release)


def download_build(nvr, base_url, session):
    """
    Download an NVR from chacra to a nvr-named directory.

    :param nvr: build NVR to download, eg ceph-ansible_3.2.0~rc3-2redhat1
    :param base_url: chacra base URL
    :param session: persistent requests.Session() to use for HTTPS requests
    :returns: destination directory for this build
    """
    (pkg, version) = name_version(nvr)
    dest_dir = os.path.join('downloads', nvr)
    ensure_directory(dest_dir)
    build_url = posixpath.join(base_url, 'binaries/', pkg, version,
                               'ubuntu', 'all')
    log.info('searching %s for builds' % build_url)
    build_response = session.get(build_url)
    build_response.raise_for_status()
    payload = build_response.json()
    for arch, binaries in payload.items():
        metadata_url = posixpath.join(build_url, arch)
        metadata_response = session.get(metadata_url)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        for binary in binaries:
            output_path = os.path.join(dest_dir, binary)
            if os.path.isfile(output_path):
                checksum = metadata[binary]['checksum']
                if verify_checksum(output_path, checksum):
                    log.info('skipping %s' % binary)
                    continue
                else:
                    log.warning('checksum mismatch on %s' % binary)
            log.info('downloading %s' % binary)
            binary_url = posixpath.join(build_url, arch, binary) + '/'
            r = session.get(binary_url, stream=True)
            r.raise_for_status()
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(4096):
                    f.write(chunk)
    return dest_dir


def verify_checksum(path, checksum):
    """
    Verify this local file's sha512 against checksum.

    :param path: file to check
    :param checksum: expected checksum value
    """
    chsum = sha512()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            chsum.update(chunk)
        digest = chsum.hexdigest()
    return digest == checksum
