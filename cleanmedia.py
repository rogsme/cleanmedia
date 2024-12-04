"""Main cleanmedia module."""

"""
CleanMedia.
Copyright (C) 2024 Sebastian Spaeth

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import List, Optional, Tuple, Union

try:
    import psycopg2  # noqa: E401
    import psycopg2.extensions
    import yaml
except ImportError as err:
    raise Exception("Please install psycopg2 and pyyaml") from err


# ------------------------------------------------------------------------
class File:
    """Represent a file in our db together with physical file and thumbnails."""

    def __init__(self, media_repo: "MediaRepository", media_id: str, creation_ts: int, base64hash: str):
        """Initialize a File object."""
        self.repo = media_repo
        self.media_id = media_id
        self.create_date = datetime.fromtimestamp(creation_ts)
        self.base64hash = base64hash

    @cached_property
    def fullpath(self) -> Optional[Path]:
        """Returns the directory in which the "file" and all thumbnails are located, or None if no file is known."""
        if not self.base64hash:
            return None
        return self.repo.media_path / self.base64hash[0:1] / self.base64hash[1:2] / self.base64hash[2:]

    def delete(self) -> bool:
        """Remove db entries and the file itself.

        :returns: True on successful delete of file,
                 False or Exception on failure
        """
        res = True
        if self.fullpath is None:
            logging.info(f"No known path for file id '{self.media_id}', cannot delete file.")
            res = False
        elif not self.fullpath.is_dir():
            logging.debug(f"Path for file id '{self.media_id}' is not a directory or does not exist, not deleting.")
            res = False
        else:
            for file in self.fullpath.glob("*"):
                # note: this does not handle directories in fullpath
                file.unlink()
            self.fullpath.rmdir()
            logging.debug(f"Deleted directory {self.fullpath}")

        with self.repo.conn.cursor() as cur:
            cur.execute("DELETE from mediaapi_thumbnail WHERE media_id=%s;", (self.media_id,))
            num_thumbnails = cur.rowcount
            cur.execute("DELETE from mediaapi_media_repository WHERE media_id=%s;", (self.media_id,))
            num_media = cur.rowcount
        self.repo.conn.commit()
        logging.debug(f"Deleted {num_media} + {num_thumbnails} db entries for media id {self.media_id}")
        return res

    def exists(self) -> bool:
        """Return True if the media file exists on the file system."""
        if self.fullpath is None:
            return False
        return (self.fullpath / "file").exists()

    def has_thumbnail(self) -> int:
        """Return the number of thumbnails associated with this file."""
        with self.repo.conn.cursor() as cur:
            cur.execute(f"select COUNT(media_id) from mediaapi_thumbnail WHERE media_id='{self.media_id}';")
            row = cur.fetchone()
            if row is None:
                return 0
        return int(row[0])


class MediaRepository:
    """Handle a dendrite media repository."""

    def __init__(self, media_path: Path, connection_string: str):
        """Initialize a MediaRepository object."""
        self.media_path = media_path
        if not self.media_path.is_absolute():
            logging.warn("The media path is relative, make sure you run this script in the correct directory!")
        if not self.media_path.is_dir():
            raise Exception("The configured media dir cannot be found!")
        self._avatar_media_ids: List[str] = []

        self.db_conn_string = connection_string
        self.conn = self.connect_db()

    def connect_db(self) -> psycopg2.extensions.connection:
        """Return a connection to the database."""
        if self.db_conn_string is None or not self.db_conn_string.startswith(("postgres://", "postgresql://")):
            errstr = "DB connection not a postgres one"
            logging.error(errstr)
            raise ValueError(errstr)
        return psycopg2.connect(self.db_conn_string)

    def get_single_media(self, mxid: str) -> Optional[File]:
        """Return a File object or None for given media ID."""
        with self.conn.cursor() as cur:
            sql_str = "SELECT media_id, creation_ts, base64hash from mediaapi_media_repository WHERE media_id = %s;"
            cur.execute(sql_str, (mxid,))
            row = cur.fetchone()
            if row is None:
                return None
            # creation_ts is ms since the epoch, so convert to seconds
            return File(self, row[0], row[1] // 1000, row[2])

    def get_local_user_media(self, user_id: str) -> List[File]:
        """Return all media created by a local user.

        :params:
           :user_id: (`str`) of form "@user:servername.com"
        :returns: `List[File]`
        """
        with self.conn.cursor() as cur:
            sql_str = "SELECT media_id, creation_ts, base64hash from mediaapi_media_repository WHERE user_id = %s;"
            cur.execute(sql_str, (user_id,))
            files = []
            for row in cur.fetchall():
                # creation_ts is ms since the epoch, so convert to seconds
                f = File(self, row[0], row[1] // 1000, row[2])
                files.append(f)
        return files

    def get_all_media(self, local: bool = False) -> List[File]:
        """Return a list of remote media or ALL media if local==True."""
        with self.conn.cursor() as cur:
            sql_str = "SELECT media_id, creation_ts, base64hash from mediaapi_media_repository"
            if not local:
                sql_str += " WHERE user_id = ''"
            sql_str += ";"
            cur.execute(sql_str)
            files = []
            for row in cur.fetchall():
                f = File(self, row[0], row[1] // 1000, row[2])
                files.append(f)
        return files

    def get_avatar_images(self) -> List[str]:
        """Return a list of media_id which are current avatar images.

        We don't want to clean up those. Save & cache them internally.
        """
        media_id = []
        with self.conn.cursor() as cur:
            cur.execute("SELECT avatar_url FROM userapi_profiles WHERE avatar_url > '';")
            for row in cur.fetchall():
                url = row[0]  # mxc://matrix.org/6e627f4c538563
                try:
                    media_id.append(url[url.rindex("/") + 1 :])
                except ValueError:
                    logging.warn("No slash in URL '%s'!", url)
            self._avatar_media_ids = media_id
        return self._avatar_media_ids

    def sanity_check_thumbnails(self) -> None:
        """Check for thumbnails in db that don't refer to existing media."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(media_id) from mediaapi_thumbnail "
                "WHERE NOT EXISTS (SELECT media_id FROM mediaapi_media_repository);",
            )
            row = cur.fetchone()
            if row is not None and row[0]:
                logging.error(
                    "You have {} thumbnails in your db that do not refer to media. "
                    "This needs fixing (we don't do that)!".format(row[0]),
                )

    def clean_media_files(self, days: int, local: bool = False, dryrun: bool = False) -> int:
        """Remove old media files from this repository.

        :params:
           :days: (int) delete media files older than N days.
           :local: (bool) Also delete media originating from local users
           :dryrun: (bool) Do not actually delete any files (just count)
        :returns: (int) The number of files that were/would be deleted
        """
        if local:
            # populate the cache of current avt img. so we don't delete them
            self.get_avatar_images()

        cleantime = datetime.today() - timedelta(days=days)
        logging.info("Deleting remote media older than %s", cleantime)
        num_deleted = 0
        files = self.get_all_media(local)
        for file in [f for f in files if f.media_id not in self._avatar_media_ids]:
            if file.create_date < cleantime:
                num_deleted += 1
                if dryrun:  # the great pretender
                    logging.info(f"Pretending to delete file id {file.media_id} on path {file.fullpath}.")
                    if not file.exists():
                        logging.info(f"File id {file.media_id} does not physically exist (path {file.fullpath}).")
                else:
                    file.delete()
        info_str = "Deleted %d files during the run."
        if dryrun:
            info_str = "%d files would have been deleted during the run."
        logging.info(info_str, num_deleted)

        return num_deleted


# --------------------------------------------------------------
def read_config(conf_file: Union[str, Path]) -> Tuple[Path, str]:
    """Return db credentials and media path from dendrite config file."""
    try:
        with open(conf_file) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        errstr = f"Config file {conf_file} not found. Use the --help option to find out more."
        logging.error(errstr)
        sys.exit(1)

    if "media_api" not in config:
        logging.error("Missing section media_api")
        sys.exit(1)

    CONN_STR = None
    if "global" in config and "database" in config["global"]:
        CONN_STR = config["global"]["database"].get("connection_string", None)
    elif "database" in config["media_api"]:
        logging.debug("No database section in global, but one in media_api, using that")
        CONN_STR = config["media_api"]["database"].get("connection_string", None)

    if CONN_STR is None:
        logging.error("Did not find connection string to media database.")
        sys.exit(1)

    BASE_PATH = Path(config["media_api"].get("base_path", None))

    if BASE_PATH is None:
        logging.error("Missing base_path in media_api")
        sys.exit(1)
    return (BASE_PATH, CONN_STR)


def parse_options() -> argparse.Namespace:
    """Return parsed command line options."""
    loglevel = logging.INFO
    parser = argparse.ArgumentParser(
        prog="cleanmedia",
        description="Deletes 30 day old remote media files from dendrite servers",
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="location of the dendrite.yaml config file.")
    parser.add_argument("-m", "--mxid", dest="mxid", help="Just delete media <MXID>. (no cleanup otherwise)")
    parser.add_argument(
        "-u",
        "--userid",
        dest="userid",
        help=(
            "Delete all media by local user '\\@user:domain.com'. "
            "(ie, a user on hour homeserver. no cleanup otherwise)"
        ),
    )
    parser.add_argument("-t", "--days", dest="days", default="30", type=int, help="Keep remote media for <DAYS> days.")
    parser.add_argument("-l", "--local", action="store_true", help="Also purge local (ie, from *our* users) media.")
    parser.add_argument("-n", "--dryrun", action="store_true", help="Dry run (don't actually modify any files).")
    parser.add_argument("-q", "--quiet", action="store_true", help="Reduce output verbosity.")
    parser.add_argument("-d", "--debug", action="store_true", help="Increase output verbosity.")
    args: argparse.Namespace = parser.parse_args()
    if args.debug:
        loglevel = logging.DEBUG
    elif args.quiet:
        loglevel = logging.WARNING
    logging.basicConfig(level=loglevel, format="%(levelname)s - %(message)s")
    return args


if __name__ == "__main__":
    args = parse_options()
    (MEDIA_PATH, CONN_STR) = read_config(args.config)
    mr = MediaRepository(MEDIA_PATH, CONN_STR)

    if args.mxid:
        logging.info("Attempting to delete media '%s'", args.mxid)
        file = mr.get_single_media(args.mxid)
        if file:
            logging.info("Found media with id '%s'", args.mxid)
            if not args.dryrun:
                file.delete()
    elif args.userid:
        logging.info("Attempting to delete media by user '%s'", args.userid)
        files = mr.get_local_user_media(args.userid)
        num_deleted = 0
        for file in files:
            num_deleted += 1
            if args.dryrun:
                logging.info(f"Pretending to delete file id {file.media_id} on path {file.fullpath}.")
            else:
                file.delete()
        info_str = "Deleted %d files during the run."
        if args.dryrun:
            info_str = "%d files would have been deleted during the run."
        logging.info(info_str, num_deleted)

    else:
        mr.sanity_check_thumbnails()
        mr.clean_media_files(args.days, args.local, args.dryrun)
