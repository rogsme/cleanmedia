"""Tests for cleanmedia module."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Tuple
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from cleanmedia import File, MediaRepository, parse_options, process_single_media, process_user_media, read_config


@pytest.fixture
def mock_db_conn(mocker: MockerFixture) -> Tuple[Any, Any]:
    """Create mock database connection and cursor.

    Args:
        mocker: pytest-mock fixture

    Returns:
        Tuple of mock connection and cursor
    """
    conn_mock = mocker.Mock()
    cursor_mock = mocker.Mock()
    ctx_manager = mocker.Mock()
    ctx_manager.__enter__ = mocker.Mock(return_value=cursor_mock)
    ctx_manager.__exit__ = mocker.Mock(return_value=None)
    conn_mock.cursor.return_value = ctx_manager
    return conn_mock, cursor_mock


@pytest.fixture
def media_repo(tmp_path: Any, mock_db_conn: Tuple[Any, Any], mocker: MockerFixture) -> MediaRepository:
    """Create MediaRepository instance with mocked database connection.

    Args:
        tmp_path: pytest temporary directory fixture
        mock_db_conn: Mock database connection fixture
        mocker: pytest-mock fixture

    Returns:
        Configured MediaRepository instance
    """
    conn_mock, _ = mock_db_conn
    media_path = tmp_path / "media"
    media_path.mkdir()
    mocker.patch("cleanmedia.MediaRepository.connect_db", return_value=conn_mock)
    return MediaRepository(media_path, "postgresql://fake")


def test_file_init(mocker: MockerFixture) -> None:
    """Test File class initialization."""
    repo = mocker.Mock()
    file = File(repo, "mxid123", 1600000000, "base64hash123")
    assert file.media_id == "mxid123"
    assert file.create_date == datetime.fromtimestamp(1600000000)
    assert file.base64hash == "base64hash123"
    assert file.repo == repo


def test_file_fullpath(media_repo: MediaRepository) -> None:
    """Test File.fullpath property returns correct path."""
    file = File(media_repo, "mxid123", 1600000000, "abc123")
    expected_path = media_repo.media_path / "a" / "b" / "c123"
    assert file.fullpath == expected_path


def test_file_exists_no_path(media_repo: MediaRepository) -> None:
    """Test File.exists returns False when fullpath is None."""
    file = File(media_repo, "mxid123", 1600000000, "")  # Empty hash ensures fullpath is None
    assert file.exists() is False


def test_file_delete_no_path(media_repo: MediaRepository) -> None:
    """Test File._delete_files when file path is None."""
    file = File(media_repo, "mxid123", 1600000000, "")
    assert file._delete_files() is False


def test_file_delete_oserror(media_repo: MediaRepository, mocker: MockerFixture, caplog: Any) -> None:
    """Test File._delete_files when OSError occurs."""
    file = File(media_repo, "mxid123", 1600000000, "abc123")

    # Create directory structure
    file_path = media_repo.media_path / "a" / "b" / "c123"
    file_path.mkdir(parents=True)
    (file_path / "file").touch()

    # Mock Path.glob to raise OSError
    mocker.patch.object(Path, "glob", side_effect=OSError("Permission denied"))

    assert file._delete_files() is False
    assert "Failed to delete files for mxid123: Permission denied" in caplog.text


def test_file_fullpath_none_if_no_hash(media_repo: MediaRepository) -> None:
    """Test File.fullpath returns None when hash is empty."""
    file = File(media_repo, "mxid123", 1600000000, "")
    assert file.fullpath is None


def test_file_exists(media_repo: MediaRepository) -> None:
    """Test File.exists returns True when file exists."""
    file = File(media_repo, "mxid123", 1600000000, "abc123")
    file_path = media_repo.media_path / "a" / "b" / "c123"
    file_path.mkdir(parents=True)
    (file_path / "file").touch()
    assert file.exists() is True


def test_file_not_exists(media_repo: MediaRepository) -> None:
    """Test File.exists returns False when file doesn't exist."""
    file = File(media_repo, "mxid123", 1600000000, "abc123")
    assert file.exists() is False


def test_file_delete(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any]) -> None:
    """Test File.delete removes files and database entries."""
    _, cursor_mock = mock_db_conn
    file = File(media_repo, "mxid123", 1600000000, "abc123")

    file_path = media_repo.media_path / "a" / "b" / "c123"
    file_path.mkdir(parents=True)
    (file_path / "file").touch()
    (file_path / "thumb").touch()

    assert file.delete() is True
    assert not file_path.exists()

    cursor_mock.execute.assert_any_call("DELETE from mediaapi_thumbnail WHERE media_id=%s;", ("mxid123",))
    cursor_mock.execute.assert_any_call("DELETE from mediaapi_media_repository WHERE media_id=%s;", ("mxid123",))


def test_get_single_media(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any]) -> None:
    """Test MediaRepository.get_single_media returns correct File object."""
    _, cursor_mock = mock_db_conn
    cursor_mock.fetchone.return_value = ("mxid123", 1600000000000, "abc123")

    file = media_repo.get_single_media("mxid123")
    assert file is not None
    assert file.media_id == "mxid123"
    assert file.base64hash == "abc123"

    cursor_mock.execute.assert_called_with(
        "SELECT media_id, creation_ts, base64hash from mediaapi_media_repository WHERE media_id = %s;",
        ("mxid123",),
    )


def test_get_single_media_not_found(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any]) -> None:
    """Test MediaRepository.get_single_media returns None when media not found."""
    _, cursor_mock = mock_db_conn
    cursor_mock.fetchone.return_value = None

    file = media_repo.get_single_media("mxid123")
    assert file is None


def test_clean_media_files(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any]) -> None:
    """Test MediaRepository.clean_media_files deletes old files."""
    _, cursor_mock = mock_db_conn

    old_date = int((datetime.now() - timedelta(days=31)).timestamp())
    new_date = int((datetime.now() - timedelta(days=1)).timestamp())

    cursor_mock.fetchall.return_value = [
        ("old_file", old_date * 1000, "abc123"),
        ("new_file", new_date * 1000, "def456"),
    ]

    media_repo._avatar_media_ids = []

    num_deleted = media_repo.clean_media_files(30, False, False)
    assert num_deleted == 1


def test_clean_media_files_dryrun(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any]) -> None:
    """Test MediaRepository.clean_media_files in dry run mode."""
    _, cursor_mock = mock_db_conn

    old_date = int((datetime.now() - timedelta(days=31)).timestamp())
    cursor_mock.fetchall.return_value = [
        ("old_file", old_date * 1000, "abc123"),
    ]

    media_repo._avatar_media_ids = []

    num_deleted = media_repo.clean_media_files(30, False, True)
    assert num_deleted == 1


def test_clean_media_files_local(media_repo: MediaRepository, mocker: MockerFixture) -> None:
    """Test clean_media_files fetches avatar images when local=True."""
    mock_get_avatars = mocker.patch.object(media_repo, "get_avatar_images")
    media_repo.get_all_media = mocker.Mock(return_value=[])  # type: ignore

    media_repo.clean_media_files(30, local=True)
    mock_get_avatars.assert_called_once()


def test_sanity_check_thumbnails(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any], caplog: Any) -> None:
    """Test MediaRepository.sanity_check_thumbnails logs correct message."""
    _, cursor_mock = mock_db_conn
    cursor_mock.fetchone.return_value = (5,)

    media_repo.sanity_check_thumbnails()
    assert "You have 5 thumbnails in your db that do not refer to media" in caplog.text


def test_get_avatar_images(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any]) -> None:
    """Test MediaRepository.get_avatar_images returns correct list."""
    _, cursor_mock = mock_db_conn
    cursor_mock.fetchall.return_value = [
        ("mxc://matrix.org/abc123",),
        ("mxc://matrix.org/def456",),
    ]

    avatar_ids = media_repo.get_avatar_images()
    assert avatar_ids == ["abc123", "def456"]


def test_get_avatar_images_invalid_url(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any], caplog: Any) -> None:
    """Test get_avatar_images with invalid URL."""
    _, cursor_mock = mock_db_conn
    cursor_mock.fetchall.return_value = [("invalid_url",)]

    avatar_ids = media_repo.get_avatar_images()
    assert avatar_ids == []
    assert "Invalid avatar URL: invalid_url" in caplog.text


def test_validate_media_path_absolute(tmp_path: Path) -> None:
    """Test _validate_media_path with absolute path."""
    MediaRepository._validate_media_path(tmp_path)


def test_validate_media_path_not_exists(tmp_path: Path) -> None:
    """Test _validate_media_path with non-existent directory."""
    invalid_path = tmp_path / "nonexistent"
    with pytest.raises(ValueError, match="Media directory not found"):
        MediaRepository._validate_media_path(invalid_path)


def test_validate_media_path_relative(caplog: Any) -> None:
    """Test _validate_media_path with relative path."""
    relative_path = Path(".")
    MediaRepository._validate_media_path(relative_path)
    assert "Media path is relative" in caplog.text


def test_connect_db_success(mocker: MockerFixture) -> None:
    """Test successful database connection."""
    mock_connect = mocker.patch("psycopg2.connect")
    repo = MediaRepository(Path("/tmp"), "postgresql://fake")
    repo.connect_db()
    mock_connect.assert_called_with("postgresql://fake")


def test_connect_db_invalid_string(tmp_path: Path) -> None:
    """Test connect_db with invalid connection string."""
    with pytest.raises(ValueError, match="Invalid PostgreSQL connection string"):
        repo = MediaRepository(tmp_path, "invalid")
        repo.connect_db()


def test_get_local_user_media(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any]) -> None:
    """Test get_local_user_media returns correct files."""
    _, cursor_mock = mock_db_conn
    cursor_mock.fetchall.return_value = [
        ("media1", 1600000000000, "hash1"),
        ("media2", 1600000000000, "hash2"),
    ]

    files = media_repo.get_local_user_media("@user:domain.com")
    assert len(files) == 2  # noqa PLR2004
    assert files[0].media_id == "media1"
    assert files[1].media_id == "media2"

    cursor_mock.execute.assert_called_with(
        "SELECT media_id, creation_ts, base64hash FROM mediaapi_media_repository WHERE user_id = %s;",
        ("@user:domain.com",),
    )


def test_process_single_media(media_repo: MediaRepository) -> None:
    """Test process_single_media deletes file."""
    args = MagicMock()
    args.mxid = "test_media"
    args.dryrun = False

    file_mock = MagicMock()
    media_repo.get_single_media = MagicMock(return_value=file_mock)  # type: ignore

    process_single_media(media_repo, args)

    media_repo.get_single_media.assert_called_once_with("test_media")
    file_mock.delete.assert_called_once()


def test_process_user_media(media_repo: MediaRepository) -> None:
    """Test process_user_media deletes all user files."""
    args = MagicMock()
    args.userid = "@test:domain.com"
    args.dryrun = False

    file1, file2 = MagicMock(), MagicMock()
    media_repo.get_local_user_media = MagicMock(return_value=[file1, file2])  # type: ignore

    process_user_media(media_repo, args)

    media_repo.get_local_user_media.assert_called_once_with("@test:domain.com")
    file1.delete.assert_called_once()
    file2.delete.assert_called_once()


def test_read_config_missing_file() -> None:
    """Test read_config with missing config file."""
    with pytest.raises(SystemExit):
        read_config("nonexistent.yaml")


def test_read_config_invalid_content(tmp_path: Path) -> None:
    """Test read_config with invalid config content."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("invalid: true")

    with pytest.raises(SystemExit):
        read_config(config_file)


def test_read_config_valid(tmp_path: Path) -> None:
    """Test read_config with valid config."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
media_api:
    base_path: /media/path
    database:
        connection_string: postgresql://user:pass@localhost/db
""")

    path, conn_string = read_config(config_file)
    assert path == Path("/media/path")
    assert conn_string == "postgresql://user:pass@localhost/db"


def test_read_config_global_database(tmp_path: Path) -> None:
    """Test read_config gets connection string from global database section."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
media_api:
    base_path: /media/path
global:
    database:
        connection_string: postgresql://global/db
""")

    path, conn_string = read_config(config_file)
    assert conn_string == "postgresql://global/db"


def test_read_config_missing_conn_string(tmp_path: Path) -> None:
    """Test read_config exits when connection string is missing."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
media_api:
    base_path: /media/path
    database: {}
""")

    with pytest.raises(SystemExit):
        read_config(config_file)


def test_read_config_missing_base_path(tmp_path: Path) -> None:
    """Test read_config exits when base_path is missing."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
media_api:
    database:
        connection_string: postgresql://fake/db
""")

    with pytest.raises(SystemExit):
        read_config(config_file)


def test_parse_options_defaults(mocker: MockerFixture) -> None:
    """Test parse_options default values."""
    mocker.patch("sys.argv", ["cleanmedia"])
    args = parse_options()

    assert args.config == "config.yaml"
    assert args.days == 30  # noqa PLR2004
    assert not args.local
    assert not args.dryrun


def test_file_has_thumbnails(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any]) -> None:
    """Test File.has_thumbnail returns correct count."""
    _, cursor_mock = mock_db_conn
    cursor_mock.fetchone.return_value = (3,)

    file = File(media_repo, "mxid123", 1600000000, "abc123")
    assert file.has_thumbnail() == 3  # noqa PLR2004
    cursor_mock.execute.assert_called_with(
        "SELECT COUNT(media_id) FROM mediaapi_thumbnail WHERE media_id = %s;",
        ("mxid123",),
    )


def test_file_has_no_thumbnails(media_repo: MediaRepository, mock_db_conn: Tuple[Any, Any]) -> None:
    """Test File.has_thumbnail returns 0 when no thumbnails exist."""
    _, cursor_mock = mock_db_conn
    cursor_mock.fetchone.return_value = None

    file = File(media_repo, "mxid123", 1600000000, "abc123")
    assert file.has_thumbnail() == 0
