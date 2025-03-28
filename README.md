# Cleanmedia
[![codecov](https://codecov.io/gl/rogs/cleanmedia/graph/badge.svg?token=CXOM5OQ76L)](https://codecov.io/gl/rogs/cleanmedia)

<p align="center">
  <img src="https://gitlab.com/uploads/-/system/project/avatar/64971838/logo.png" alt="cleanmedia"/>
</p>

A data retention policy tool for Dendrite servers.

## Special thanks

The original author of this script is Sebastian Spaeth ([sspaeth](https://gitlab.com/sspaeth)). All props to him!

## Overview

Cleanmedia helps manage media storage on Dendrite servers by implementing configurable retention policies for both remote and local media files. It can remove old media files based on age while preserving essential content like user avatars.

## Installation

### Using Docker (Recommended)

The easiest way to run Cleanmedia is using Docker. You can either use it as a standalone container or integrate it with your docker-compose.yml:

```yaml
services:
  cleanmedia:
    hostname: cleanmedia
    image: rogsme/cleanmedia
    volumes:
      - /your/dendrite/config/location:/etc/dendrite
      - /your/dendrite/media/location:/var/dendrite/media
    environment:
      - CRON=0 0 * * *  # Run daily at midnight
      - CLEANMEDIA_OPTS=-c /etc/dendrite/dendrite.yaml -t 30 -l  # 30 day retention, include local files
    depends_on:
      - monolith
```
⚠ **MAKE SURE YOUR MOUNTPOINTS CORRESPOND TO THE MOUNTPOINTS OF YOUR DENDRITE DOCKER INSTALLATION!**

#### Environment Variables

- `CRON`: Cron schedule expression (default: `0 0 * * *` - daily at midnight)
- `CLEANMEDIA_OPTS`: Command line options for cleanmedia (default: `-c /etc/dendrite/dendrite.yaml -t 30 -n -l`)

#### Docker Volume Mounts

- `/etc/dendrite`: Dendrite configuration directory
- `/var/dendrite/media`: Dendrite media storage directory

### Manual Installation

Cleanmedia uses uv for dependency management. To install:

```bash
# Install uv if you haven't already
pip install uv

# Install dependencies
uv sync
```

#### Requirements

- Python >= 3.9
- uv for dependency management
- Required packages (automatically installed by uv):
  - psycopg2
  - pyyaml
  - Development dependencies for testing and linting

## Usage

### Command Line Options

- `-c`, `--config`: Path to dendrite.yaml config file (default: config.yaml)
- `-m`, `--mxid`: Delete a specific media ID
- `-u`, `--userid`: Delete all media from a local user ('@user:domain.com')
- `-t`, `--days`: Keep remote media for specified number of days (default: 30)
- `-l`, `--local`: Include local user media in cleanup
- `-n`, `--dryrun`: Simulate cleanup without modifying files
- `-q`, `--quiet`: Reduce output verbosity
- `-d`, `--debug`: Increase output verbosity

### Docker Usage Examples

1. Run with default settings (daily cleanup, 30-day retention):
```bash
docker compose up -d cleanmedia
```

2. Run with custom schedule and options:
```yaml
environment:
  - CRON=0 */6 * * *  # Run every 6 hours
  - CLEANMEDIA_OPTS=-c /etc/dendrite/dendrite.yaml -t 14 -l -d  # 14 day retention with debug logging
```

3. Run a one-off cleanup:
```bash
docker compose run --rm cleanmedia python cleanmedia.py -c /etc/dendrite/dendrite.yaml -t 1 -l -d -n
```

### Manual Usage

```bash
uv run cleanmedia.py --help
```

### How it Works

#### Remote Media Purge (Default)
- Scans database for media entries where user_id is empty (remote media)
- Deletes entries and files older than the specified retention period
- Includes cleanup of associated thumbnails
- Preserves remote avatar images of users

#### Local Media Purge (Optional)
- Activated with the `-l` flag
- Removes media uploaded by local server users
- Preserves user avatar images
- Use with caution as local media might not be retrievable after deletion

### Sanity Checks

The tool performs consistency checks and warns about:
- Thumbnails in the database without corresponding media entries
- Missing files that should exist according to the database
- Invalid file paths or permissions issues

## Development

### Testing

The project includes a comprehensive test suite using pytest:

```bash
# Run tests
uv run pytest

# Run tests with coverage report
uv run pytest --cov=. --cov-report=xml

# Run specific test file
uv run pytest tests/test_cleanmedia.py
```

### Code Quality

Multiple tools ensure code quality:

```bash
# Run linting
uv run ruff check

# Run formatting check
uv run ruff format --check

# Run type checking
uv run mypy .
```

The project uses pre-commit hooks for consistent code quality. Install them with:

```bash
uv run pre-commit install
```

## License

This code is released under the GNU GPL v3 or any later version.

**Warning**: There is no warranty for correctness or data that might be accidentally deleted. Use with caution and always test with `--dryrun` first!

## Contributing

Contributions are welcome! Please ensure you:
1. Add tests for new functionality
2. Follow the existing code style (enforced by ruff)
3. Update documentation as needed
4. Run the test suite and linting before submitting PRs
