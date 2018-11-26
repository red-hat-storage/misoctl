import json
import os
import shutil
from koji_cli.lib import _progress_callback
from koji_cli.lib import watch_tasks
try:
    # Available in Koji v1.17, https://pagure.io/koji/issue/975
    from koji_cli.lib import unique_path
except ImportError:
    from koji_cli.lib import _unique_path as unique_path
from misoctl import filemanager
from misoctl import util
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
    parser.add_argument('--skip-log', action='store_true',
                        help="Do not upload a .build log file")
    parser.add_argument('directory', help="parent directory of a .dsc file")
    parser.set_defaults(func=main)


def get_build_data(dsc, start_time, end_time, scm_url, owner):
    """ Return a dict of build information, for the CG metadata. """
    name = '%s-deb' % dsc['Source']
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
    checksum = util.get_md5sum(filename)
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
        callback = _progress_callback
        log.info("Uploading %s" % filename)
        session.uploadWrapper(filename, remote_directory, callback=callback)
        if callback:
            print('')
    return remote_directory


def cg_import(all_files, metadata, session):
    """
    Import all files into this Koji content generator.

    :param all_files: set of files to upload and import
    :param metadata: path to metadata json file
    :param session: Koji session
    :returns: buildinfo (dict) from Koji's CGImport call
    """
    remote_directory = upload(all_files, session)
    buildinfo = session.CGImport(metadata, remote_directory)
    if not buildinfo:
        raise RuntimeError('CGImport failed')
    return buildinfo


def tag_build(buildinfo, tag, session):
    """ Tag this build in Koji. """
    nvr = '%(name)s-%(version)s-%(release)s' % buildinfo
    log.info('tagging %s into %s' % (nvr, tag))
    task_id = session.tagBuild(tag, nvr)
    task_result = watch_tasks(session, [task_id], poll_interval=15)
    if task_result != 0:
        raise RuntimeError('failed to tag builds')


def import_from_directory(directory, session, owner, skip_log, scm_url,
                          dryrun):
    """
    Import the build artifacts in this directory into a Koji CG build.

    :param directory: dir containing the build artifacts, with one dsc file.
    :param session: Koji session.
    :param owner: Koji user to own this imported build.
    :param skip_log: Don't try to import log files for this build.
    :param scm_url: SCM (dist-git) url for this build.
    :param dryrun: show what would be done, but don't do it.
    """
    # Discover our files on disk
    dsc_file = filemanager.find_dsc_file(directory)
    dsc = filemanager.parse_dsc(dsc_file)
    source_files = filemanager.find_source_files(dsc, directory)
    deb_files = filemanager.find_deb_files(directory)
    log_files = set()
    log_file = filemanager.find_log_file(directory, fatal=skip_log)
    if log_file:
        log_file = rename_log_file(log_file)
        log_files.add(log_file)

    # Bail early if this build already exists
    nvr = '%(Source)s-deb-%(Version)s' % dsc
    if session.getBuild(nvr):
        raise RuntimeError('%s build exists in koji' % nvr)

    # Determine build metadata
    if log_file:
        (start_time, end_time) = filemanager.get_build_times(log_file)
    else:
        # This is not optimial, because the start and end times are the same,
        # so it looks as if the build took zero seconds.
        changes_file = filemanager.find_changes_file(directory)
        changes_time = filemanager.get_changes_time(changes_file)
        start_time = changes_time
        end_time = changes_time
    build = get_build_data(dsc, start_time, end_time, scm_url, owner)

    # Determine buildroot metadata
    buildroots = get_buildroots()

    # Determine output metadata
    dsc_files = set([dsc_file])
    all_files = set.union(dsc_files, source_files, deb_files, log_files)
    output = get_output_data(all_files)

    # Generate the main metdata JSON
    metadata = get_metadata(build, buildroots, output)
    with open('metadata.json', 'w') as f:
        json.dump(metadata, f)
    all_files.add('metadata.json')

    # TODO: check if this build already exists in Koji before uploading here

    if dryrun:
        log.info('dryrun: would upload')
        for filename in all_files:
            log.info(filename)
        return {}
    buildinfo = cg_import(all_files, metadata, session)
    return buildinfo


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
        verify_tag(tag, session)

    buildinfo = import_from_directory(directory,
                                      session,
                                      args.owner,
                                      args.skip_log,
                                      args.scm_url,
                                      args.dryrun)
    log.info('imported %(name)s-%(version)s-%(release)s' % buildinfo)

    if tag:
        tag_build(buildinfo, tag, session)
    else:
        log.info('not tagging %(name)s-%(version)s-%(release)s' % buildinfo)
