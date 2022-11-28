Cleanmedia
==========

A poor man's data retention policy for dendrite servers.

USAGE
=====

Check the command line options with --help. You mainly pass it the dendrite
configuration file as a means to find a) the media directory and b) the postgres
credentials for the dendrite data base.

How it works:
-------------

cleanmedia scours the database for all entries in the media repository where
user_id is an empty string (that is, the media was not uploaded by a local user). It then deletes all entries that have been created <X> time ago. (with X being hardcoded for now to be 30 days)

Todo
----

- Sanity checks: Are files on the file system that the db does not
  know about?
- Sanity checks: Are there thumbnails in the db that do not have
  corresponding media file entries?

LICENSE
=======

This code is released under the GNU GPL v3 or any later version.