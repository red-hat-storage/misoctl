import pytest
from misoctl import sync_chacra


KOJI_NVRS = [
    ('ceph_1.2-1', 'ceph-deb-1.2-1'),
    ('ceph-deploy_1.2-1', 'ceph-deploy-deb-1.2-1'),
]


@pytest.mark.parametrize('deb_nvr,expected', KOJI_NVRS)
def test_get_koji_nvr(deb_nvr, expected):
    result = sync_chacra.get_koji_nvr(deb_nvr)
    assert result == expected
