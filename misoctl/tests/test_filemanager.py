from misoctl import filemanager


def test_find_dsc_file(tmpdir):
    dscfile = tmpdir.ensure('mypackage_1.0-1.dsc', file=True)
    tmpdir.ensure('mypackage_1.0-1.deb', file=True)
    expected = str(dscfile)
    directory = str(tmpdir)
    return filemanager.find_dsc_file(directory) == expected


def test_find_deb_files(tmpdir):
    tmpdir.ensure('mypackage_1.0-1.dsc', file=True)
    debfile = tmpdir.ensure('mypackage_1.0-1.deb', file=True)
    expected = set([str(debfile)])
    directory = str(tmpdir)
    return filemanager.find_deb_files(directory) == expected
