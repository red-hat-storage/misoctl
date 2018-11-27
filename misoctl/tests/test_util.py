from misoctl import util


def test_get_md5sum(tmpdir):
    cache_file = tmpdir.join('mypackage_1.0-1.deb')
    try:
        cache_file.write_binary(b'testpackagecontents')
    except AttributeError:
        # python-py < v1.4.24 does not support write_binary()
        cache_file.write('testpackagecontents')
    expected = 'e04a72f793a87ba9e1b48000044a5e2b'
    filename = str(cache_file)
    assert util.get_md5sum(filename) == expected
