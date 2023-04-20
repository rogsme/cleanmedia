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
files that have been created `DAYS` time ago. (with DAYS being
configurable via command line and a default of 30 days)

This includes a number of remote media that we might want to keep
(e.g. avatar images of users on remote home servers).

But the main idea behind focusing on remote media is that a server
should be able to refetch remote media in case it is needed. It would
also make sense to delete local media, but that is more
complicated. (possible scenarios: local media older than Y days, rooms
that have been left by all users and are thus "unreachable", rooms that
have been upgraded but have users left in it, media that has not been "accessed" the last Y days,....)

But finding out these things and setting all these policies will be
way more difficult and in some cases we do not have the information
we'd need (e.g. if a media is part of an avatar image, or when media
has been accessed the last time).

In addition it performs some sanity checks and warns if inconsistencies occur:
 1) Are there thumbnails in the db that do not have
    corresponding media file entries (in the db)?

Todo
----

- Sanity checks: Are files on the file system that the db does not
  know about?

LICENSE
=======

This code is released under the GNU GPL v3 or any later version.

There is no warranty for correctness or data that might be
accidentally deleted. Assume the worst and hope for the best!