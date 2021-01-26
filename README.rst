misoctl
=======

.. image:: https://travis-ci.org/red-hat-storage/misoctl.svg?branch=master
             :target: https://travis-ci.org/red-hat-storage/misoctl

Upload Debian builds to Koji as a content generator.

Example
-------

Here's an example of building a package, uploading the artifacts to Koji, and
tagging the resulting build::

   # Clone a Debian package (ceph-ansible) from Git:
   SCM_URL=git://example.com/ceph-ansible
   git clone $SCM_URL
   cd mypackage

   # Build the package: 
   gbp buildpackage ...

   # Upload the source and .deb artifacts into Koji:
   misoctl upload \
     --scm-url=$SCM_URL \
     --owner=kdreyer \
     --tag=ceph-3.2-xenial-candidate \
     ../

To run this utility, you must authenticate to Koji as a user account that has
permission to upload to the "debian" content generator.

Example: Sync'ing many lists of builds
--------------------------------------

Use the "sync-chacra" command to sync several lists of builds into Koji::

   # Clone a list of Debian builds Git:
   git clone git://example.com/rhcs-metadata.git

   tree rhcs-metadata
    rhcs-metadata/
    ├── ceph-2
    │   ├── builds-ceph-2.0-22986-trusty.txt
    │   ├── builds-ceph-2.0-22986-xenial.txt
    │   ├── builds-ceph-2.0-async-24474-trusty.txt
    │   ├── builds-ceph-2.0-async-24474-xenial.txt
    │   ├── builds-ceph-2.1-25020-trusty.txt
    │   ├── builds-ceph-2.1-25020-xenial.txt
    │   ├── builds-ceph-2.1-async-25856-trusty.txt
    │   ├── builds-ceph-2.1-async-25856-xenial.txt
    ...

   # Crawl this tree of build .txt files, ensuring that all the builds exist in
   # Koji:
   misoctl sync-chacra \
      --chacra-url https://chacra.example.com \
      --scm-template "https://code.example.com/{name}" \
      --owner kdreyer \
      rhcs-metadata/

Warning: if you run ``sync-chacra`` multiple times, Koji can update the
"latest" build in a tag on each run. You may desire this behavior if you're
using this in a limited way, only ever adding higher NVRs to your build txt
lists over time. On the other hand, if you run it with a small subset of build
txt lists, and then run it again with *older* build lists, this could end up
tagging older builds as "newer". In other words, please use caution when using
``sync-chacra``, and don't run it with build txt lists that are older than what
you've already imported and tagged in Koji.


Example: Finding missing build artifacts
----------------------------------------

Chacra might not contain all the files we need (because of various bugs in the
build system over the years). Use the "missing-chacra" sub-command to
sanity-check each build and report these inconsistencies::

   # Clone a list of Debian builds Git:
   git clone git://example.com/rhcs-metadata.git

   tree rhcs-metadata
    rhcs-metadata/
    ├── ceph-2
    │   ├── builds-ceph-2.0-22986-trusty.txt
    │   ├── builds-ceph-2.0-22986-xenial.txt
    │   ├── builds-ceph-2.0-async-24474-trusty.txt
    │   ├── builds-ceph-2.0-async-24474-xenial.txt
    │   ├── builds-ceph-2.1-25020-trusty.txt
    │   ├── builds-ceph-2.1-25020-xenial.txt
    ...

   # Crawl this tree of build .txt files, ensuring that all artifacts exist:
   misoctl missing-chacra \
      --chacra-url https://chacra.example.com \
      rhcs-metadata/

This command only uses chacra. It does not use Koji at all.


Koji server configuration
-------------------------

You must configure your Koji instance to accept debian builds.

As a Koji administrator:

1. Allow "debian" content-generator access to a system user account. In this
   case, our system user account is named "rcm/debbuild"::

      koji grant-cg-access rcm/debbuild debian

2. Add the debian build type to Koji::

      koji call addBType debian

3. Add the debian source archive type (needs the new `addArchiveType RPC
   <https://pagure.io/koji/pull-request/1149>`_ on the Koji hub)::

      koji call addArchiveType dsc "Debian source control files" dsc

4. If you are running Koji prior to 1.24, add the ``deb`` file archivetype as
   well::

      koji call addArchiveType deb "Debian packages" deb

   This is `already available <https://pagure.io/koji/issue/2575>`_ in Koji
   1.24.

Now you can run ``misoctl upload`` as the ``rcm/debbuild`` system user.

About the Name
--------------

This tool is similar to `chacractl <https://pypi.org/project/chacractl/>`_, and
Koji is an ingredient in Miso.
