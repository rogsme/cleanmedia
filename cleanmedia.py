"""Media cleanup utility for Dendrite servers."""

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
from typing import List, Tuple, TypeAlias, Union

try:
    import psycopg2
    import psycopg2.extensions
    import yaml
except ImportError as err:
    raise ImportError("Required dependencies not found. Please install psycopg2 and pyyaml.") from err

# Type aliases
DBConnection: TypeAlias = psycopg2.extensions.connection
MediaID: TypeAlias = str
Timestamp: TypeAlias = int
Base64Hash: TypeAlias = str
UserID: TypeAlias = str


class File:
    """Represent a media file with its metadata and physical storage location."""

    def __init__(
        self,
        media_repo: "MediaRepository",
        media_id: MediaID,
        creation_ts: Timestamp,
        base64hash: Base64Hash,
    ) -> None:
        """Initialize a File object."""
        self.repo = media_repo
        self.media_id = media_id
        self.create_date = datetime.fromtimestamp(creation_ts)
        self.base64hash = base64hash

    @cached_property
    def fullpath(self) -> Path | None:
        """Get the directory containing the file and its thumbnails.

        Returns:
            Path to directory or None if no file location is known
        """
        if not self.base64hash:
            return None
        return self.repo.media_path / self.base64hash[0:1] / self.base64hash[1:2] / self.base64hash[2:]

    def delete(self) -> bool:
        """Remove file from filesystem and database.

        Returns:
            True if deletion was successful, False otherwise
        """
        if not self._delete_files():
            return False

        return self._delete_db_entries()

    def _delete_files(self) -> bool:
        """Remove physical files from filesystem.

        Returns:
            True if files were deleted or didn't exist, False on error
        """
        if self.fullpath is None:
            logging.info(f"No known path for file id '{self.media_id}', cannot delete file.")
            return False

        if not self.fullpath.is_dir():
            logging.debug(f"Path for file id '{self.media_id}' is not a directory or does not exist.")
            return False

        try:
            for file in self.fullpath.glob("*"):
                file.unlink()
            self.fullpath.rmdir()
            logging.debug(f"Deleted directory {self.fullpath}")
            return True
        except OSError as err:
            logging.error(f"Failed to delete files for {self.media_id}: {err}")
            return False

    def _delete_db_entries(self) -> bool:
        """Remove file entries from database.

        Returns:
            True if database entries were deleted successfully
        """
        with self.repo.conn.cursor() as cur:
            cur.execute("DELETE from mediaapi_thumbnail WHERE media_id=%s;", (self.media_id,))
            num_thumbnails = cur.rowcount
            cur.execute("DELETE from mediaapi_media_repository WHERE media_id=%s;", (self.media_id,))
            num_media = cur.rowcount
        self.repo.conn.commit()
        logging.debug(f"Deleted {num_media} + {num_thumbnails} db entries for media id {self.media_id}")
        return True

    def exists(self) -> bool:
        """Check if the media file exists on the filesystem.

        Returns:
            True if file exists, False otherwise
        """
        if self.fullpath is None:
            return False
        return (self.fullpath / "file").exists()

    def has_thumbnail(self) -> int:
        """Count thumbnails associated with this file.

        Returns:
            Number of thumbnails
        """
        with self.repo.conn.cursor() as cur:
            cur.execute("SELECT COUNT(media_id) FROM mediaapi_thumbnail WHERE media_id = %s;", (self.media_id,))
            row = cur.fetchone()
            return int(row[0]) if row else 0


class MediaRepository:
    """Handle media storage and retrieval for a Dendrite server."""

    def __init__(self, media_path: Path, connection_string: str) -> None:
        """Initialize MediaRepository.

        Args:
            media_path: Path to media storage directory
            connection_string: PostgreSQL connection string

        Raises:
            ValueError: If media_path doesn't exist or connection string is invalid
        """
        self._validate_media_path(media_path)
        self.media_path = media_path
        self._avatar_media_ids: List[MediaID] = []
        self.db_conn_string = connection_string
        self.conn = self.connect_db()

    @staticmethod
    def _validate_media_path(path: Path) -> None:
        if not path.is_absolute():
            logging.warning("Media path is relative. Ensure correct working directory!")
        if not path.is_dir():
            raise ValueError("Media directory not found")

    def connect_db(self) -> DBConnection:
        """Establish database connection.

        Returns:
            PostgreSQL connection object

        Raises:
            ValueError: If connection string is invalid
        """
        if not self.db_conn_string or not self.db_conn_string.startswith(("postgres://", "postgresql://")):
            raise ValueError("Invalid PostgreSQL connection string")
        return psycopg2.connect(self.db_conn_string)

    def get_single_media(self, mxid: MediaID) -> File | None:
        """Retrieve a single media file by ID."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT media_id, creation_ts, base64hash from mediaapi_media_repository WHERE media_id = %s;",
                (mxid,),
            )
            row = cur.fetchone()
            return File(self, row[0], row[1] // 1000, row[2]) if row else None

    def get_local_user_media(self, user_id: UserID) -> List[File]:
        """Get all media files created by a local user.

        Args:
            user_id: User ID in format "@user:servername.com"

        Returns:
            List of File objects
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT media_id, creation_ts, base64hash FROM mediaapi_media_repository WHERE user_id = %s;",
                (user_id,),
            )
            return [File(self, row[0], row[1] // 1000, row[2]) for row in cur.fetchall()]

    def get_all_media(self, local: bool = False) -> List[File]:
        """Get all media files or only remote ones.

        Args:
            local: If True, include local media files

        Returns:
            List of File objects
        """
        with self.conn.cursor() as cur:
            query = """SELECT media_id, creation_ts, base64hash
                      FROM mediaapi_media_repository"""
            if not local:
                query += " WHERE user_id = ''"
            cur.execute(query)
            return [File(self, row[0], row[1] // 1000, row[2]) for row in cur.fetchall()]

    def get_avatar_images(self) -> List[MediaID]:
        """Get media IDs of current avatar images.

        Returns:
            List of media IDs
        """
        with self.conn.cursor() as cur:
            cur.execute("SELECT avatar_url FROM userapi_profiles WHERE avatar_url > '';")
            media_ids = []
            for (url,) in cur.fetchall():
                try:
                    media_ids.append(url[url.rindex("/") + 1 :])
                except ValueError:
                    logging.warning("Invalid avatar URL: %s", url)
            self._avatar_media_ids = media_ids
            return media_ids

    def sanity_check_thumbnails(self) -> None:
        """Check for orphaned thumbnail entries in database."""
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(media_id) FROM mediaapi_thumbnail
                   WHERE NOT EXISTS (SELECT media_id FROM mediaapi_media_repository);""",
            )
            if (row := cur.fetchone()) and (count := row[0]):
                logging.error(
                    "You have %d thumbnails in your db that do not refer to media. "
                    "This needs fixing (we don't do that)!",
                    count,
                )

    def clean_media_files(self, days: int, local: bool = False, dryrun: bool = False) -> int:
        """Remove old media files.

        Args:
            days: Delete files older than this many days
            local: If True, include local media files
            dryrun: If True, only simulate deletion

        Returns:
            Number of files deleted (or that would be deleted in dryrun mode)
        """
        if local:
            self.get_avatar_images()

        cutoff_date = datetime.today() - timedelta(days=days)
        logging.info("Deleting remote media older than %s", cutoff_date)

        files_to_delete = [
            f
            for f in self.get_all_media(local)
            if f.media_id not in self._avatar_media_ids and f.create_date < cutoff_date
        ]

        for file in files_to_delete:
            if dryrun:
                logging.info(f"Would delete file {file.media_id} at {file.fullpath}")
                if not file.exists():
                    logging.info(f"File {file.media_id} doesn't exist at {file.fullpath}")
            else:
                file.delete()

        action = "Would have deleted" if dryrun else "Deleted"
        logging.info("%s %d files", action, len(files_to_delete))
        return len(files_to_delete)


def read_config(conf_file: Union[str, Path]) -> Tuple[Path, str]:
    """Read database credentials and media path from config.

    Args:
        conf_file: Path to Dendrite YAML config file

    Returns:
        Tuple of (media_path, connection_string)

    Raises:
        SystemExit: If config file is invalid or missing required fields
    """
    try:
        with open(conf_file) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logging.error("Config file %s not found. Use --help for usage.", conf_file)
        sys.exit(1)

    if "media_api" not in config:
        logging.error("Missing media_api section in config")
        sys.exit(1)

    conn_string = None
    if "global" in config and "database" in config["global"]:
        conn_string = config["global"]["database"].get("connection_string")
    elif "database" in config["media_api"]:
        logging.debug("Using database config from media_api section")
        conn_string = config["media_api"]["database"].get("connection_string")

    if not conn_string:
        logging.error("Database connection string not found in config")
        sys.exit(1)

    base_path = config["media_api"].get("base_path")
    if not base_path:
        logging.error("base_path not found in media_api config")
        sys.exit(1)

    return Path(base_path), conn_string


def parse_options() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed argument namespace
    """
    parser = argparse.ArgumentParser(prog="cleanmedia", description="Delete old media files from Dendrite servers")
    parser.add_argument("-c", "--config", default="config.yaml", help="Path to dendrite.yaml config file")
    parser.add_argument("-m", "--mxid", help="Delete specific media ID")
    parser.add_argument("-u", "--userid", help="Delete all media from local user '@user:domain.com'")
    parser.add_argument("-t", "--days", type=int, default=30, help="Keep remote media for DAYS days")
    parser.add_argument("-l", "--local", action="store_true", help="Include local user media in cleanup")
    parser.add_argument("-n", "--dryrun", action="store_true", help="Simulate cleanup without modifying files")
    parser.add_argument("-q", "--quiet", action="store_true", help="Reduce output verbosity")
    parser.add_argument("-d", "--debug", action="store_true", help="Increase output verbosity")

    args = parser.parse_args()

    log_level = logging.INFO
    if args.debug:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s - %(message)s")

    return args


def main() -> None:
    """Execute the media cleanup process."""
    args = parse_options()
    media_path, conn_string = read_config(args.config)
    repo = MediaRepository(media_path, conn_string)

    if args.mxid:
        process_single_media(repo, args)
    elif args.userid:
        process_user_media(repo, args)
    else:
        repo.sanity_check_thumbnails()
        repo.clean_media_files(args.days, args.local, args.dryrun)


def process_single_media(repo: MediaRepository, args: argparse.Namespace) -> None:
    """Handle deletion of a single media file.

    Args:
        repo: MediaRepository instance
        args: Parsed command line arguments
    """
    logging.info("Attempting to delete media '%s'", args.mxid)
    if file := repo.get_single_media(args.mxid):
        logging.info("Found media with id '%s'", args.mxid)
        if not args.dryrun:
            file.delete()


def process_user_media(repo: MediaRepository, args: argparse.Namespace) -> None:
    """Handle deletion of all media from a user.

    Args:
        repo: MediaRepository instance
        args: Parsed command line arguments
    """
    logging.info("Attempting to delete media by user '%s'", args.userid)
    files = repo.get_local_user_media(args.userid)

    for file in files:
        if args.dryrun:
            logging.info("Would delete file %s at %s", file.media_id, file.fullpath)
        else:
            file.delete()

    action = "Would delete" if args.dryrun else "Deleted"
    logging.info("%s %d files", action, len(files))


if __name__ == "__main__":
    main()
