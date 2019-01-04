import os
import posixpath
import requests
import StringIO
from debian import deb822
from misoctl.sync_chacra import find_all_nvrs, sort_nvrs
from misoctl.chacra import name_version
from misoctl.log import log as log


DESCRIPTION = """
Find all the Chacra builds that are missing files.

This walks a tree of rhcephcompose builds-*.txt files and ensures that we have
a dsc file, all the files mentioned in the dsc file, and a changes file.
"""


class SourceError(Exception):
    """ Somthing was wrong with this NVR's sources. """
    pass


class NoFilesFoundException(SourceError):
    """ This NVR lacks a source file. """
    pass


class MultipleFilesFoundException(SourceError):
    """ This NVR has too many of the expected source files. """
    pass


def add_parser(subparsers):
    """
    Add build parser to this top-level subparsers object.
    """
    parser = subparsers.add_parser('missing-chacra', description=DESCRIPTION,
                                   help='find missing files in chacra')

    parser.add_argument('--chacra-url', required=True,
                        help='Chacra base URL to use, eg. https://...')
    parser.add_argument('directory', default='.',
                        help="directory tree of build txt files")
    parser.set_defaults(func=main)


def find_one_url(extension, urls):
    """
    Find one and only one url for this file extension.
    """
    needle = None
    for url in urls:
        if url.endswith(extension):
            if needle:
                raise MultipleFilesFoundException('.%s' % extension)
            needle = url
    if not needle:
        raise NoFilesFoundException('.%s' % extension)
    return needle


def parse_debian(url, klass, rsession):
    """
    Download this URL and parse it into this Debian class.
    """
    response = rsession.get(url)
    response.raise_for_status()
    io = StringIO.StringIO(response.text)
    result = klass(io)
    io.close()
    return result


def ensure_files(nvr, chacra_url, rsession):
    """
    Ensure this build has all the relevant files in chacra.

    :param nvr: build's name_versionrelease in chacra
    :param chacra_url: base url to chacra instance
    :param rsession: requests.Session object
    :raises: SourceError if there was any problem with this build's sources.
    """
    source_urls = get_source_urls(nvr, chacra_url, rsession)
    source_filenames = [os.path.basename(url) for url in source_urls]
    # Check the .dsc file
    try:
        dsc_url = find_one_url('dsc', source_urls)
    except SourceError as e:
        raise e.__class__('%s: %s' % (nvr, str(e)))
    dsc = parse_debian(dsc_url, deb822.Dsc, rsession)
    if not dsc['Files']:
        raise NoFilesFoundException('no files in %s' % dsc_url)
    missing = set()
    for f in dsc['Files']:
        filename = f['name']
        if filename not in source_filenames:
            missing.add(filename)
    if missing:
        raise NoFilesFoundException('dsc links to %s' % ' '.join(missing))
    # Check the .changes file
    try:
        changes_url = find_one_url('changes', source_urls)
    except SourceError as e:
        raise e.__class__('%s: %s' % (nvr, str(e)))
    changes = parse_debian(changes_url, deb822.Changes, rsession)
    if not changes['Files']:
        raise NoFilesFoundException('no files in %s' % changes_url)


def get_source_urls(nvr, base_url, session):
    (pkg, version) = name_version(nvr)
    src_url = posixpath.join(base_url, 'binaries/', pkg, version,
                             'ubuntu', 'all', 'source')
    log.debug('searching %s for files' % src_url)
    src_response = session.get(src_url)
    if src_response.status_code == 404:
        raise NoFilesFoundException('%s has no source files' % nvr)
    src_response.raise_for_status()
    payload = src_response.json()
    urls = set()
    for filename in payload:
        url = posixpath.join(src_url, filename)
        urls.add(url)
    return urls


def main(args):
    rsession = requests.Session()

    nvrs = find_all_nvrs(args.directory)

    sorted_nvrs = sort_nvrs(nvrs.keys())

    for nvr in sorted_nvrs:
        log.debug('nvr: "%s"' % nvr)
        try:
            ensure_files(nvr, args.chacra_url, rsession)
        except SourceError as e:
            log.error('%s: %s' % (e.__class__.__name__, e))
