import os
from glob import glob
import datetime
import dateutil.parser
import dateutil.tz
from debian import deb822
from misoctl import util
from misoctl.log import log as log

"""
Find and parse various debian build files for information.
"""


class NoFilesFoundError(Exception):
    pass


class MultipleFilesFoundError(Exception):
    pass


def find_changes_file(directory):
    """ Find the path to a .changes file in this directory. """
    return find_one_file('changes', directory)


def find_deb_files(directory):
    """ Find the paths to all the .debs in this directory """
    search_path = os.path.join(directory, '*.deb')
    filenames = glob(search_path)
    return set(filenames)


def find_dsc_file(directory):
    """ Find the path to a .dsc file in this directory.  """
    return find_one_file('dsc', directory)


def find_log_file(directory, fatal=True):
    """ Find the path to a .build file in this directory. """
    try:
        return find_one_file('build', directory)
    except NoFilesFoundError:
        if fatal:
            raise


def find_one_file(extension, directory):
    """
    Search for one file with an extension in this directory.

    Raise if we could not find exactly one.
    """
    search_path = os.path.join(directory, '*.%s' % extension)
    results = glob(search_path)
    if len(results) < 1:
        raise NoFilesFoundError('could not find a .%s file in %s' %
                                (extension, directory))
    if len(results) > 1:
        log.error(results)
        raise MultipleFilesFoundError('multiple .%s files in %s' %
                                      (extension, directory))
    return results[0]


def find_source_files(dsc, directory):
    """ Find the paths to all the source files in this directory. """
    result = set()
    for f in dsc['Files']:
        filename = f['name']
        path = os.path.join(directory, filename)
        # Sanity-check the file while we're here:
        if not os.path.isfile(path):
            raise RuntimeError('dsc file references non-existent %s' % path)
        md5sum = util.get_md5sum(path)
        if md5sum != f['md5sum']:
            raise RuntimeError('dsc file md5sum mismatch on %s' % path)
        result.add(path)
    return result


def get_build_times(log_file):
    """ Return the start and end times from a pbuilder log file. """
    start_time = None
    end_time = None
    with open(log_file) as f:
        for line in f:
            if line.startswith('I: pbuilder-time-stamp: '):
                timestamp = int(line[24:].strip())
                if start_time is None:
                    start_time = timestamp
                elif end_time is None:
                    end_time = timestamp
                else:
                    log.error('reading %s' % log_file)
                    raise RuntimeError('too many pbuilder-time-stamp lines')
    if not start_time:
        raise RuntimeError('could not find start time in %s' % log_file)
    if not end_time:
        raise RuntimeError('could not find end time in %s' % log_file)
    return (start_time, end_time)


def get_changes_time(changes_file):
    """
    Get the epoch seconds value from this .changes file.

    :param changes_file: a Debian .changes file for this build.
    :returns: number of seconds since the unix epoch
    """
    changes = parse_changes(changes_file)
    changes_date = changes['Date']
    my_datetime = dateutil.parser.parse(changes_date)
    epoch = datetime.datetime(1970, 1, 1, tzinfo=dateutil.tz.UTC)
    total_seconds = (my_datetime - epoch).total_seconds()
    return total_seconds


def parse_changes(changes_file):
    """ Parse a changes file into a Changes class. """
    with open(changes_file) as f:
        return deb822.Changes(f)


def parse_dsc(dsc_file):
    """ Parse a dsc file into a Dsc class. """
    with open(dsc_file) as f:
        return deb822.Dsc(f)
