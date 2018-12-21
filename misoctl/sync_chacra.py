from collections import defaultdict
import os
import re
import sys
import requests
from koji_cli.lib import watch_tasks
from debian import debian_support
import misoctl.session
from misoctl import chacra
from misoctl import upload
from misoctl.log import log as log


DESCRIPTION = """
Synchronize all the "shipped builds" from Chacra into Koji.

This walks a tree of rhcephcompose builds-*.txt files and:
1) Ensures that the builds are all imported into Koji,
2) Ensures they the builds are all tagged with the right release tag.

This code is not entirely idempotent, particularly if run with different
directories over time. Use it for a one-time migration from Chacra to Koji.
"""


def add_parser(subparsers):
    """
    Add build parser to this top-level subparsers object.
    """
    parser = subparsers.add_parser('sync-chacra', description=DESCRIPTION,
                                   help='sync builds from chacra to Koji')

    parser.add_argument('--chacra-url', required=True,
                        help='Chacra base URL to use, eg. https://...')
    parser.add_argument('--scm-template', required=True,
                        help='SCM URL pattern template for all builds. eg. '
                             'git://example.com/packages/{name}')
    parser.add_argument('--owner', required=True,
                        help='koji user name that will own all new builds')
    parser.add_argument('--dryrun', action='store_true',
                        help="Show what would happen, but don't do it")
    parser.add_argument('directory', default='.',
                        help="directory tree of build txt files")
    parser.set_defaults(func=main)


def find_buildstxts(directory):
    buildstxts = set()
    for root, _, files in os.walk(directory):
        for filename in files:
            if re.match(r'builds-.*\.txt', filename):
                buildstxts.add(os.path.join(root, filename))
    return buildstxts


def read_nvrs(buildstxt):
    """ Find the NVRs in this builds .txt file. """
    nvrs = set()
    with open(buildstxt) as f:
        for line in f:
            stripped = line.rstrip('\n')
            if stripped:
                nvrs.add(stripped)
    return nvrs


def get_distro(string):
    distros = ('precise', 'trusty', 'xenial', 'bionic')
    for distro in distros:
        if distro in string:
            return distro
    raise ValueError('no distro in %s' % string)


def get_tag_names(path):
    """
    Determine appropriate Koji tag names from this builds txt file name.

    Our builds .txt files follow certain naming conventions.
    We'll parse this out as best we can in order to determine a tag name.

    :returns: eg set(['ceph-3.2-xenial'])
    """
    basename = os.path.basename(path)
    regex = re.compile(r'builds-(\w+-[0-9\.]+)(?:-async)?-([\w\-]+)\.txt$')
    match = regex.match(basename)
    if not match:
        raise RuntimeError('parsing %s' % basename)
    base = match.group(1)   # "ceph-3.2"
    extra = match.group(2)  # extra bit at the end of the file
    # Special case some Ceph rules.
    if base.startswith('ceph-1.3'):
        base = 'ceph-1.3'
    if base.startswith('ceph-2'):
        base = 'ceph-2'
    match = re.match(r'\d+-(precise|trusty|xenial|bionic)$', extra)
    if match:
        # standard tag here.
        distro = match.group(1)
        base_tag_name = '%s-%s' % (base, distro)
        # return set([base_tag_name, '%s-candidate' % base_tag_name])
        return set([base_tag_name])
    match = re.match(r'override-(precise|trusty|xenial|bionic)$', extra)
    if match:
        # -override tag here.
        distro = match.group(1)
        tag_name = '%s-%s-override' % (base, distro)
        return set([tag_name])
    # Everything else gets the -hotfix tag.
    distro = get_distro(extra)
    tag_name = '%s-%s-hotfix' % (base, distro)
    return set([tag_name])


def find_all_nvrs(directory):
    """
    Find all NVRs (and tag names) in this directory of builds .txt files.
    """
    all_nvrs = defaultdict(set)
    buildstxts = find_buildstxts(directory)
    for buildstxt in buildstxts:
        nvrs = read_nvrs(buildstxt)
        # Determine the Koji tag names for these NVRs as well.
        tag_names = get_tag_names(buildstxt)
        for nvr in nvrs:
            all_nvrs[nvr].update(tag_names)
    # If a build is tagged into the main release tag, don't tag it into
    # the -override or -hotfix tags as well. Tag inheritance will take care of
    # that for us (hooray).
    for nvr, tag_names in all_nvrs.items():
        for tag_name in tag_names.copy():
            base_tag_name = None
            if tag_name.endswith('-hotfix'):
                base_tag_name = tag_name[:-7]
            elif tag_name.endswith('-override'):
                base_tag_name = tag_name[:-9]
            if base_tag_name and base_tag_name in tag_names:
                all_nvrs[nvr].remove(tag_name)
    return all_nvrs


def ensure_uploaded(nvr, chacra_url, rsession, session, owner, scm_template,
                    dryrun):
    """
    Ensure this build is uploaded into Koji.

    :param nvr: build's name_versionrelease in chacra
    :param chacra_url: base url to chacra instance
    :param rsession: requests.Session object
    :param session: Koji session
    :param owner: Koji user name that will own this build
    :param scm_template: format string for this build's scm_url
    :param dryrun: if True, show what would have happened, but don't do it
    """
    koji_nvr = nvr.replace('_', '-deb-')
    # Check if this build exists in Koji
    buildinfo = session.getBuild(koji_nvr)
    if buildinfo:
        return buildinfo
    if dryrun:
        log.info('would download chacra build %s' % nvr)
        return
    directory = chacra.download_build(nvr, chacra_url, rsession)
    skip_log = True
    (name, version) = chacra.name_version(nvr)
    scm_url = scm_template.format(name=name)
    buildinfo = upload.import_from_directory(directory,
                                             session,
                                             owner,
                                             skip_log,
                                             scm_url,
                                             dryrun)
    return buildinfo


def ensure_tagged(buildinfo, tags, session, dryrun):
    """
    Ensure this build is tagged into Koji.

    :param dict buildinfo: dict from getBuild with this name/version/release
    :param list tags: list of tags for this build.
    :param session: Koji session
    :param bool dryrun: show what would happen, but don't do it.
    """
    task_ids = []
    nvr = '%(name)s-%(version)s-%(release)s' % buildinfo
    for tag in sorted(tags):
        tagged_builds = session.listTagged(tag, package=buildinfo['name'],
                                           type='debian')
        tagged_nvrs = [tagged_build['nvr'] for tagged_build in tagged_builds]
        if nvr in tagged_nvrs:
            log.info('%s is already tagged into %s' % (nvr, tag))
            continue
        log.info('tagging %s into %s' % (nvr, tag))
        if dryrun:
            continue
        task_id = session.tagBuild(tag, nvr)
        task_ids.append(task_id)
    task_result = watch_tasks(session, task_ids, poll_interval=15)
    if task_result != 0 and not dryrun:
        raise RuntimeError('failed to tag build %s' % nvr)


def compare_nvrs(a_nvr, b_nvr):
    (a_name, a_version) = chacra.name_version(a_nvr)
    (b_name, b_version) = chacra.name_version(b_nvr)
    if sys.version_info[0] < 3:
        compare_names = cmp(a_name, b_name)  # NOQA: F821
    else:
        compare_names = (a_name > b_name) - (a_name < b_name)
    if compare_names != 0:
        return compare_names
    return debian_support.version_compare(a_version, b_version)


def sort_nvrs(nvrs):
    if sys.version_info[0] < 3:
        return sorted(nvrs, cmp=compare_nvrs)
    from functools import cmp_to_key
    return sorted(nvrs, key=cmp_to_key(compare_nvrs))


def main(args):

    # Pre-flight checks
    directory = args.directory
    assert os.path.isdir(directory)

    rsession = requests.Session()
    session = misoctl.session.get_session(args.profile)

    upload.verify_user(args.owner, session)

    nvrs = find_all_nvrs(directory)

    sorted_nvrs = sort_nvrs(nvrs.keys())

    for nvr in sorted_nvrs:
        log.info('nvr: "%s"' % nvr)
        buildinfo = ensure_uploaded(nvr,
                                    args.chacra_url,
                                    rsession,
                                    session,
                                    args.owner,
                                    args.scm_template,
                                    args.dryrun)

        if args.dryrun and not buildinfo:
            # Minimally fake the buildinfo we would have generated above.
            (name, version, release) = chacra.name_version_release(nvr)
            buildinfo = {'name': name, 'version': version, 'release': release}
        tags = nvrs[nvr]
        ensure_tagged(buildinfo, tags, session, args.dryrun)
