# NOTE: I broke down and switched over to using Synapse, so while the tool works great, don't expect any further efforts from my side. If you want to take over maintainership, let me know (@spaetz:sspaeth.de).

# Cleanmedia

A poor man's data retention policy for dendrite servers.

## USAGE

Check the command line options with --help. You mainly pass it the dendrite
configuration file as a means to find a) the media directory and b) the postgres
credentials for the dendrite data base.

You can also pass in the number of days you want to keep remote
media. Optionally, you may also purge media from local users on the
homeserver.

### How it works

#### Purge remote media (default)

cleanmedia scours the database for all entries in the media repository
where user_id is an empty string (that is, the media was not uploaded
by a local user). It then deletes all entries, thumbnails and media
files that have been created `DAYS` time ago. (with DAYS being
configurable via command line and a default of 30 days)

This includes a number of remote media that we might want to keep
(e.g. avatar images of users on remote home servers).

The main idea behind focusing on remote media is that a server
should be able to refetch remote media in case it is needed.

#### Purging "local" media (optional)

It also makes sense to delete local media, and it is possible using the
option -l, but that is more complicated. (Local means, originating by
users on our homeserver.)

a) we might be the only source of our user's media, so any local media
that we purge might not be retrievable by anyone anymore - ever.

b) it is not easy to decide which local media are safe to purge.

Possible scenarios: local media older than Y days, rooms that have been
left by all users and are thus "unreachable", rooms that have been
upgraded but have users left in it, media that has not been "accessed"
the last Y days, ....

Finding out these things and setting all these policies is way more
difficult and in some cases we do not have the information we'd need
(e.g. when media has been accessed the last time).

Right now, we purge all older local media, except for user avatar
images.

#### Sanity checks

In addition, we perform some sanity checks and warns if inconsistencies
occur:

1) Are there thumbnails in the db that do not have corresponding media
    file entries (in the db)?

## Requirements

 - Python >= 3.8
 - psycopg2
 - yaml


## Todo

- Sanity checks: Are files on the file system that the db does not
  know about?

## LICENSE

This code is released under the GNU GPL v3 or any later version.

**There is no warranty for correctness or data that might be
accidentally deleted. Assume the worst and hope for the best!**
