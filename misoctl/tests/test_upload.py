import misoctl.upload as upload


def test_get_md5sum(tmpdir):
    cache_file = tmpdir.join('mypackage_1.0-1.deb')
    try:
        cache_file.write_binary(b'testpackagecontents')
    except AttributeError:
        # python-py < v1.4.24 does not support write_binary()
        cache_file.write('testpackagecontents')
    expected = 'e04a72f793a87ba9e1b48000044a5e2b'
    filename = str(cache_file)
    assert upload.get_md5sum(filename) == expected


def test_find_dsc_file(tmpdir):
    dscfile = tmpdir.ensure('mypackage_1.0-1.dsc', file=True)
    tmpdir.ensure('mypackage_1.0-1.deb', file=True)
    expected = str(dscfile)
    directory = str(tmpdir)
    return upload.find_dsc_file(directory) == expected


def test_find_deb_files(tmpdir):
    tmpdir.ensure('mypackage_1.0-1.dsc', file=True)
    debfile = tmpdir.ensure('mypackage_1.0-1.deb', file=True)
    expected = set([str(debfile)])
    directory = str(tmpdir)
    return upload.find_deb_files(directory) == expected
