import pytest
from misoctl import chacra


@pytest.mark.parametrize('nvr,expected', (
    ('ceph_1.2-1', ('ceph', '1.2-1')),
    ('ceph-deploy_1.2-1', ('ceph-deploy', '1.2-1')),
    ('ceph-deploy_1.2', ('ceph-deploy', '1.2')),
))
def test_name_version(nvr, expected):
    result = chacra.name_version(nvr)
    assert result == expected


@pytest.mark.parametrize('nvr', ('foo', 'foo_bar_', '_foo_bar'))
def test_bad_name_version(nvr):
    with pytest.raises(ValueError):
        chacra.name_version(nvr)


@pytest.mark.parametrize('nvr,expected', (
    ('ceph_1.2-1', ('ceph', '1.2', '1')),
    ('ceph-deploy_1.2-1', ('ceph-deploy', '1.2', '1')),
    ('ceph-deploy_1.2', ('ceph-deploy', '1.2', '0')),
))
def test_name_version_release(nvr, expected):
    result = chacra.name_version_release(nvr)
    assert result == expected


@pytest.fixture
def pkg_file(tmpdir):
    """ A simple package file on local disk """
    local_file = tmpdir.join('mypackage_1.0-1.deb')
    try:
        local_file.write_binary(b'testpackagecontents')
    except AttributeError:
        # python-py < v1.4.24 does not support write_binary()
        local_file.write('testpackagecontents')
    return local_file


def test_verify_checksum(pkg_file):
    checksum = 'cce64bfb35285d9c5d82e0a083cafcc6afa3292b84b26f567d92ea8ccd420e57881c9218e718c73a2ce23af53ad05ab54f168cd28ee1b5ca7ca23697fa887e1e'  # NOQA: E501
    filename = str(pkg_file)
    assert chacra.verify_checksum(filename, checksum)


def test_verify_checksum_fails(pkg_file):
    checksum = 'f00badlolz'
    filename = str(pkg_file)
    assert not chacra.verify_checksum(filename, checksum)
