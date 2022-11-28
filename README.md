Cleanmedia
==========

A poor man's data retention policy for dendrite servers.

USAGE
=====

Check the command line options with --help. You mainly pass it the dendrite
configuration file as a means to find a) the media directory and b) the postgres
credentials for the dendrite data base.

You can also pass in the number of days you want to keep remote media.

How it works:
-------------

cleanmedia scours the database for all entries in the media repository
where user_id is an empty string (that is, the media was not uploaded
by a local user). It then deletes all entries, thumbnails and media
files that have been created <DAYS> time ago. (with DAYS being
configurable via command line and a default of 30 days)

The main idea behind focusing on remote media is that a server should
be able to refetch remote media in case it is needed. It would also
make sense to delete local media, but that is more
complicated. (possible scenarios: older than Y days, rooms that have
been left by all users and are "unreachable", rooms that have been
upgraded but have users left in it,....)

Todo
----

- Sanity checks: Are files on the file system that the db does not
  know about?
- Sanity checks: Are there thumbnails in the db that do not have
  corresponding media file entries?

LICENSE
=======

This code is released under the GNU GPL v3 or any later version.