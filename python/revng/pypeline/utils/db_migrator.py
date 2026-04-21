#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import os
import re
from abc import ABC, abstractmethod
from pathlib import Path


class DBMigrator(ABC):
    def __init__(self, migrations_dir: Path):
        assert migrations_dir.is_dir()

        self._migrations: dict[int, Path] = {}
        with os.scandir(migrations_dir) as it:
            for entry in it:
                assert entry.is_file()
                match = re.match(r"v(?P<version>\d+)\.sql", entry.name)
                assert match is not None
                self._migrations[int(match["version"])] = Path(entry.path).resolve()

        for value in range(1, len(self._migrations) + 1):
            assert value in self._migrations

        self.last_version = max(self._migrations)

    @abstractmethod
    def _create_tables_if_missing(self):
        """Create the migration table if missing"""

    @abstractmethod
    def _get_last_migration(self) -> int:
        """Get the last migration number present in the DB"""

    @abstractmethod
    def _apply_migration(self, version: int, body: str):
        """Apply the specified migration to the DB"""

    def migrate(self):
        self._create_tables_if_missing()
        db_version = self._get_last_migration()
        if self.last_version == db_version:
            return

        for version in range(db_version + 1, self.last_version + 1):
            self._apply_migration(version, self._migrations[version].read_text())
