# Cleanmedia
[![codecov](https://codecov.io/gl/rogs/cleanmedia/graph/badge.svg?token=CXOM5OQ76L)](https://codecov.io/gl/rogs/cleanmedia)

A data retention policy tool for Dendrite servers.

## Special thanks

The original author of this script is Sebastian Spaeth ([sspaeth](https://gitlab.com/sspaeth)). All props to him!

## Overview

Cleanmedia helps manage media storage on Dendrite servers by implementing configurable retention policies for both remote and local media files. It can remove old media files based on age while preserving essential content like user avatars.

## Installation

Cleanmedia uses Poetry for dependency management. To install:

```bash
# Install Poetry if you haven't already
pip install poetry

# Install dependencies
poetry install
```

### Requirements

- Python >= 3.9
- Poetry for dependency management
- Required packages (automatically installed by Poetry):
  - psycopg2
  - pyyaml
  - Development dependencies for testing and linting

## Usage

Check the command line options with `--help`. The main functionality requires:
1. A Dendrite configuration file (to locate the media directory and PostgreSQL credentials)
2. Optionally, the number of days to retain remote media
3. Additional flags to control behavior

```bash
poetry run python cleanmedia.py --help
```

### Command Line Options

- `-c`, `--config`: Path to dendrite.yaml config file (default: config.yaml)
- `-m`, `--mxid`: Delete a specific media ID
- `-u`, `--userid`: Delete all media from a local user ('@user:domain.com')
- `-t`, `--days`: Keep remote media for specified number of days (default: 30)
- `-l`, `--local`: Include local user media in cleanup
- `-n`, `--dryrun`: Simulate cleanup without modifying files
- `-q`, `--quiet`: Reduce output verbosity
- `-d`, `--debug`: Increase output verbosity

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
poetry run pytest

# Run tests with coverage report
poetry run pytest --cov=. --cov-report=xml

# Run specific test file
poetry run pytest tests/test_cleanmedia.py
```

### Code Quality

Multiple tools ensure code quality:

```bash
# Run linting
poetry run ruff check

# Run formatting check
poetry run ruff format --check

# Run type checking
poetry run mypy .
```

The project uses pre-commit hooks for consistent code quality. Install them with:

```bash
poetry run pre-commit install
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
