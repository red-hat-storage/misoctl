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
   cd ..
   misoctl upload \
     --scm-url=$SCM_URL \
     --owner=kdreyer \
     --tag=ceph-3.2-xenial-candidate \
     ceph-ansible/

To run this utility, you must authenticate to Koji as a user account that has
permission to upload to the "debian" content generator.

Koji server configuration
-------------------------

You must configure your Koji instance to accept debian builds.

As a Koji administrator:

1. Allow "debian" content-generator access to a system account. In this case
   ours is named "rcm/debbuild"::

      koji grant-cg-access rcm/debbuild debian

2. Add the debian build type to Koji::

      koji call addBType debian

3. Add the debian archive types (needs the new `addArchiveType RPC
   <https://pagure.io/koji/pull-request/1149>` on the Koji hub)::

      koji call addArchiveType deb "Debian packages" deb
      koji call addArchiveType dsc "Debian source contro files" dsc


Now you can run ``misoctl upload`` as the ``rcm/debbuild`` system user.

About the Name
--------------

This tool is similar to `chacractl <https://pypi.org/project/chacractl/>`_, and
Koji is an ingredient in Miso.
