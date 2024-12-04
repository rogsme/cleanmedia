"""Tests for cleanmedia module."""

from datetime import datetime, timedelta
from typing import Any, Tuple

import pytest
from pytest_mock import MockerFixture

from cleanmedia import File, MediaRepository


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
