from glob import glob
from hashlib import md5
import json
import os
import shutil
from debian import deb822
from koji_cli.lib import _progress_callback
from koji_cli.lib import watch_tasks
try:
    # Available in Koji v1.17, https://pagure.io/koji/issue/975
    from koji_cli.lib import unique_path
except ImportError:
    from koji_cli.lib import _unique_path as unique_path
import misoctl.session
from misoctl.log import log as log


def add_parser(subparsers):
    """
    Add build parser to this top-level subparsers object.
    """
    parser = subparsers.add_parser('upload', help='upload build to Koji')

    parser.add_argument('--scm-url', required=True,
                        help='SCM URL for this build, eg. git://...')
    parser.add_argument('--owner', required=True,
                        help='koji user name that owns this build')
    parser.add_argument('--tag',
                        help='tag this build, eg. ceph-3.2-xenial-candidate')
    parser.add_argument('--dryrun', action='store_true',
                        help="Show what would happen, but don't do it")
    parser.add_argument('directory', help="parent directory of a .dsc file")
    parser.set_defaults(func=main)


def get_md5sum(filename):
    """ Return the hex md5 digest for a file. """
    chsum = md5()
    with open(filename, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            chsum.update(chunk)
    digest = chsum.hexdigest()
    return digest


def find_dsc_file(directory):
    """ Find the path to a .dsc file in this directory.  """
    return find_one_file('dsc', directory)


def find_deb_files(directory):
    """ Find the paths to all the .debs in this directory """
    search_path = os.path.join(directory, '*.deb')
    filenames = glob(search_path)
    return set(filenames)


def parse_dsc(dsc_file):
    """ Parse a dsc file into a Dsc class. """
    with open(dsc_file) as f:
        return deb822.Dsc(f)


def get_build_data(dsc, start_time, end_time, scm_url, owner):
    """ Return a dict of build information, for the CG metadata. """
    name = dsc['Source']
    version, release = dsc['Version'].split('-')
    info = {
        'name': name,
        'version': version,
        'release': release,
        'source': scm_url,
        'start_time': start_time,
        'end_time': end_time,
        'owner': owner,
        'extra': {
            'typeinfo': {
                'debian': {},
            },
        },
    }
    return info


def get_output_data(filenames):
    """ Return a list of file information, for the CG metadata. """
    output = []
    for filename in filenames:
        file_info = get_file_info(filename)
        output.append(file_info)
    return output


def get_file_info(filename):
    """ Return information about a single file, for the CG metadata. """
    info = {'buildroot_id': 0}
    info['filename'] = os.path.basename(filename)
    fbytes = os.path.getsize(filename)
    info['filesize'] = int(fbytes)
    # Kojihub only supports checksum_type: md5 for now.
    info['checksum_type'] = 'md5'
    checksum = get_md5sum(filename)
    info['checksum'] = checksum
    info['arch'] = 'x86_64'
    if filename.endswith('.tar.gz') or filename.endswith('.tar.xz'):
        info['type'] = 'tarball'
    elif filename.endswith('.deb'):
        info['type'] = 'deb'
    elif filename.endswith('.dsc'):
        info['type'] = 'dsc'
    elif filename.endswith('.log'):
        info['type'] = 'log'
    else:
        raise RuntimeError('unknown extension for %s' % filename)
    info['extra'] = {
        'typeinfo': {
            'debian': {},
        },
    }
    return info


def find_source_files(dsc, directory):
    """ Find the paths to all the source files in this directory. """
    result = set()
    for f in dsc['Files']:
        filename = f['name']
        path = os.path.join(directory, filename)
        assert os.path.isfile(path)
        result.add(path)
    return result


def find_log_file(directory):
    """ Find the path to a .build file in this directory. """
    return find_one_file('build', directory)


def rename_log_file(log_file):
    """
    Rename a .build file to a .log file.

    Koji checks each file's extension during an import operation. We have to
    do this so Koji will accept the log file when we import it.
    """
    assert log_file.endswith('.build')
    new_log_file = log_file[:-6] + '.log'
    # os.rename(log_file, new_log_file)
    # I'm copying instead of renaming, for testing:
    shutil.copy(log_file, new_log_file)
    return new_log_file


def find_one_file(extension, directory):
    """
    Search for one file with an extension in this directory.

    Raise if we could not find exactly one.
    """
    search_path = os.path.join(directory, '*.%s' % extension)
    results = glob(search_path)
    if len(results) < 1:
        raise RuntimeError('could not find a .%s file in %s' %
                           (extension, directory))
    if len(results) > 1:
        log.error(results)
        raise RuntimeError('multiple .%s files in %s' %
                           (extension, directory))
    return results[0]


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


def get_buildroots():
    buildroots = [{
        'id': 0,  # "can be synthetic"
        'host': {
            'arch': 'x86_64',
            'os': 'Ubuntu',
        },
        'content_generator': {
            'version': '1',
            'name': 'debian'
        },
        'container': {
            'type': 'pbuilder',
            'arch': 'x86_64',
        },
        'tools': [],
        'components': [],
    }]
    return buildroots


def get_metadata(build, buildroots, output):
    data = {
        'metadata_version': 0,
        'build': build,
        'buildroots': buildroots,
        'output': output,
    }
    return data


def verify_user(username, session):
    """ Verify that a user exists in this Koji instance """
    userinfo = session.getUser(username)
    if not userinfo:
        raise RuntimeError('username %s is not present in Koji' % username)


def verify_tag(tag, session):
    """ Verify that a tag exists in this Koji instance """
    taginfo = session.getTag(tag)
    if not taginfo:
        raise RuntimeError('tag %s is not present in Koji' % tag)


def upload(all_files, session):
    """
    Upload all files to a remote directory in Koji.
    """
    remote_directory = unique_path('cli-import')
    log.info('uploading files to %s' % remote_directory)

    for filename in all_files:
        basename = os.path.basename(filename)
        remote_path = os.path.join(remote_directory, basename)
        callback = _progress_callback
        log.info("Uploading %s" % filename)
        session.uploadWrapper(filename, remote_path, callback=callback)
        if callback:
            print('')


def cg_import(all_files, metadata, session):
    """ Import all files into this Koji content generator. """
    remote_directory = upload(all_files, session)
    buildinfo = session.CGImport(metadata, remote_directory)
    if not buildinfo:
        raise RuntimeError('CGImport failed')
    return buildinfo


def tag_build(buildinfo, tag, session):
    """ Tag this build in Koji. """
    nvr = '%(name)s-%(version)s-%(release)s' % buildinfo
    task_id = session.tagBuild(tag, nvr)
    task_result = watch_tasks(session, [task_id], {'poll_interval': 15})
    if task_result != 0:
        raise RuntimeError('failed to tag builds')


def main(args):

    # Pre-flight checks
    directory = args.directory
    assert os.path.isdir(directory)

    session = misoctl.session.get_session(args.profile)
    # TODO: verify this session is authorized to import to the debian CG.
    # Needs https://pagure.io/koji/pull-request/1160

    owner = args.owner
    verify_user(owner, session)

    tag = args.tag
    if tag:
        verify_tag(tag)

    # Discover our files on disk
    dsc_file = find_dsc_file(directory)
    dsc = parse_dsc(dsc_file)
    source_files = find_source_files(dsc, directory)
    deb_files = find_deb_files(directory)
    log_file = find_log_file(directory)
    log_file = rename_log_file(log_file)

    # Bail early if this build already exists
    nvr = '%(Source)s-%(Version)s' % dsc
    if session.getBuild(nvr):
        raise RuntimeError('%s exists in %s' % (nvr, args.profile))

    # Determine build metadata
    (start_time, end_time) = get_build_times(log_file)
    scm_url = args.scm_url
    build = get_build_data(dsc, start_time, end_time, scm_url, owner)

    # Determine buildroot metadata
    buildroots = get_buildroots()

    # Determine output metadata
    log_files = set([log_file])
    dsc_files = set([dsc_file])
    all_files = set.union(dsc_files, source_files, deb_files, log_files)
    output = get_output_data(all_files)

    # Generate the main metdata JSON
    metadata = get_metadata(build, buildroots, output)
    with open('metadata.json', 'w') as f:
        json.dump(metadata, f)
    all_files.add('metadata.json')

    # TODO: check if this build already exists in Koji before uploading here

    buildinfo = cg_import(all_files, metadata, session)
    log.info('CGImport result:')
    log.info(str(buildinfo))

    if tag:
        tag_build(buildinfo, tag, session)
    else:
        log.info('not tagging %(name)s-%(version)s-%(release)' % buildinfo)
