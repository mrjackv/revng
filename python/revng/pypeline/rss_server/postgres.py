#
# This file is distributed under the MIT License. See LICENSE.md for details.
#

import asyncio
import enum
import hashlib
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, cast

import psycopg.sql as sql
from psycopg import AsyncCursor, Connection
from psycopg.rows import DictRow, TupleRow, dict_row
from psycopg_pool import AsyncConnectionPool

from revng.pypeline.storage.util import _OBJECTID_MAXSIZE
from revng.pypeline.utils.db_migrator import DBMigrator

from .storage import AdditionalObjectEntry, CheckMetadataResult, CustomDependency
from .storage import CustomDependencyEntry, DependencyEntry, InvalidatedObject, LockCheckType
from .storage import LockRequest, ModelSetResult, ObjectEntry, ProjectMetadataRow, RSSStorage

# How many seconds before a lock is considered expired
LOCK_EXPIRY_SECONDS = 30

#
# Invalidation queries
# These queries are part of the invalidation workflow, which works in 5 steps:
# 1. Create temporary tables (`INVALIDATE_CREATE_TABLES`) to store the incoming
#    data, all these tables are suffixed with a randomly-generated string
#    `<suffix>` to allow the invalidation logic to run in parallel for multiple
#    projects
# 2. Populate the tables
# 3. Run `INVALIDATE_FIND` which uses the data provided to find the objects
#    that need to be deleted
# 4. Run `INVALIDATE_DELETE_DEPENDENCIES` which removes all the dependencies of
#    the objects that are going to be deleted
# 5. Run `INVALIDATE_DELETE_OBJECTS` which actually deletes the rows from the
#    `objects` table
#

# This is a binary mask that will be used for invalidation, thanks to the
# binary structure of ObjectID, all children are guaranteed to have the parent
# prefixed, so, to check for all children the check will be
# target_object_id <= checked_object_id <= CONCAT(target_object_id, _OBJECTID_MASK)  # noqa: E800
_OBJECTID_MASK = f"'\\x{"ff" * _OBJECTID_MAXSIZE}'::bytea"

# This query creates the temporary tables needed for invalidation, these will
# hold the temporary invalidation data so that the queries below can be run
# with all the data in the database
INVALIDATE_CREATE_TABLES = """
CREATE TEMPORARY TABLE model_paths_{suffix}(
  path TEXT NOT NULL
) ON COMMIT DROP;

CREATE TEMPORARY TABLE additional_objects_{suffix}(
  savepoint_id_start   INT NOT NULL,
  savepoint_id_end     INT NOT NULL,
  container_id         TEXT NOT NULL,
  configuration_hash   TEXT NOT NULL,
  object_id            BYTEA NOT NULL
) ON COMMIT DROP;

CREATE TEMPORARY TABLE invalidated_objects_{suffix}(
  rowid tid NOT NULL
) ON COMMIT DROP;
"""

# This query looks in the `objects` table for any object that has been
# invalidated as a result of the data in `model_paths_<suffix>` and
# `additional_objects_<suffix>`. It stores the ctid of the rows in
# `invalidated_objects_<suffix>` so that the subsequent queries can go quickly
# without useless lookups.
INVALIDATE_FIND = """
INSERT INTO invalidated_objects_{suffix}
SELECT DISTINCT objects.ctid
FROM objects
JOIN (
    SELECT savepoint_id_start, savepoint_id_end,
           configuration_hash, object_id
    FROM dependencies
    JOIN model_paths_{suffix}
      ON dependencies.model_path = model_paths_{suffix}.path
    WHERE dependencies.project_id = %s
  UNION
    SELECT savepoint_id_start, savepoint_id_end,
           configuration_hash, object_id
    FROM additional_objects_{suffix}
) AS dependencies ON TRUE
WHERE objects.project_id = %s
  AND ((
        objects.object_id >= dependencies.object_id
        AND objects.object_id <= (dependencies.object_id || {objectid_mask})
    ) OR (
        dependencies.object_id != '' AND objects.object_id = ''
    )
  )
  AND objects.configuration_hash = dependencies.configuration_hash
  AND objects.savepoint_id >= dependencies.savepoint_id_start
  AND objects.savepoint_id <= dependencies.savepoint_id_end
"""

# Delete all the rows in the `dependencies` table that were connected to
# invalidated objects
INVALIDATE_DELETE_DEPENDENCIES = """
DELETE FROM dependencies
WHERE dependencies.ctid IN (
  SELECT DISTINCT dependencies.ctid FROM dependencies
  JOIN (
    SELECT savepoint_id, container_id, configuration_hash, object_id
    FROM objects
    WHERE ctid IN (SELECT rowid FROM invalidated_objects_{suffix})
  ) AS invalidated_objects ON TRUE
  WHERE dependencies.savepoint_id_start = invalidated_objects.savepoint_id
    AND dependencies.container_id = invalidated_objects.container_id
    AND dependencies.configuration_hash = invalidated_objects.configuration_hash
    AND dependencies.object_id = invalidated_objects.object_id
)
"""

# Actually delete the objects, return the identifier of the objects deleted
INVALIDATE_DELETE_OBJECTS = """
DELETE FROM objects
USING invalidated_objects_{suffix} AS inv
WHERE objects.ctid = inv.rowid
RETURNING objects.object_id_string, objects.container_id,
          objects.savepoint_id, objects.configuration_hash
"""


class LockState(enum.IntEnum):
    """
    The state that a lock can be in. The values are explicitly set since they
    will be stored in the database.
    """

    ARTIFACT_WAITING = 0
    ARTIFACT = 1
    ANALYSIS_WAITING = 2
    ANALYSIS_READING = 3
    ANALYSIS_PENDING_COMMIT = 4
    ANALYSIS_COMMITTING = 5


class AnalysisState(enum.Enum):
    NONE = enum.auto()
    READING = enum.auto()
    WRITING = enum.auto()


@dataclass
class ProjectState:
    artifact_running: bool
    analysis_state: AnalysisState


class CheckLockResult(enum.Enum):
    MISSING = enum.auto()
    OK = enum.auto()
    EXPIRED = enum.auto()
    TYPE_MISMATCH = enum.auto()


def _join_lockstates(*values: LockState):
    return sql.SQL(",").join((sql.Literal(int(x)) for x in values))


async def _fetch_one(cursor: AsyncCursor) -> TupleRow:
    result = await cursor.fetchone()
    assert result is not None
    return result


async def _row_generator[T](cursor: AsyncCursor, transform: Callable[[TupleRow], T]) -> list[T]:
    result: list[T] = []
    async for row in cursor:
        result.append(transform(row))
    return result


class Migrator(DBMigrator):
    def __init__(self, conninfo: str):
        super().__init__(Path(__file__).parent / "postgres_migrations")
        self._connection = Connection.connect(conninfo)

    def _create_tables_if_missing(self):
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS "
            "migrations(version INT PRIMARY KEY, applied TIMESTAMPTZ NOT NULL)"
        )
        self._connection.commit()

    def _get_last_migration(self) -> int:
        result = self._connection.execute("SELECT MAX(version) FROM migrations").fetchone()
        if result is None or result[0] is None:
            return 0
        else:
            return result[0]

    def _apply_migration(self, version: int, body: str):
        self._connection.execute(body.encode())
        self._connection.execute("INSERT INTO migrations VALUES (%s, NOW())", (version,))
        self._connection.commit()


class PostgresRSSStorage(RSSStorage):
    """RSSStorage backed by PostgreSQL via psycopg 3 (async)."""

    def __init__(self, pool: AsyncConnectionPool):
        self.pool = pool
        self._cleanup_locks_task = asyncio.create_task(self._cleanup_locks())

    @classmethod
    async def build(cls, conninfo: str) -> "PostgresRSSStorage":
        Migrator(conninfo).migrate()
        pool = AsyncConnectionPool(conninfo, open=False)
        await pool.open()
        return cls(pool)

    @asynccontextmanager
    async def _connection(self):
        async with self.pool.connection() as conn:
            yield conn

    @asynccontextmanager
    async def _cursor(self):
        async with self.pool.connection() as conn:
            async with conn.transaction():
                yield conn.cursor()

    async def initialize(self):
        async with self._cursor() as cursor:
            await cursor.execute("TRUNCATE TABLE locks")

    async def close(self):
        self._cleanup_locks_task.cancel()
        await self.pool.close()

    #
    # Locking endpoints
    #

    @asynccontextmanager
    async def _advisory_lock(self, cursor: AsyncCursor, project_id: str):
        digest = hashlib.blake2b(project_id.encode(), digest_size=8).digest()
        key = int.from_bytes(digest, "little", signed=True)
        # TODO: the pg_advisory_xact_lock is global w.r.t. the postgres
        # instance, if we need to use the lock elsewhere we need to reduce the
        # hash bits (e.g. 60 bits) and use the other bits to encode the
        # "lock type"
        await cursor.execute("SELECT pg_advisory_lock(%s)", (key,))
        try:
            yield None
        finally:
            await cursor.execute("SELECT pg_advisory_unlock(%s)", (key,))

    async def _wait_lock(self, project_id: str, lock_id: str):
        # Use a dedicated connection for LISTEN so we don't block the main one
        channel = f"lock_{project_id}_{lock_id}"
        async with self._connection() as connection:
            await connection.execute(sql.SQL("LISTEN {}").format(sql.Identifier(channel)))
            async for _notify in connection.notifies():
                break

    @asynccontextmanager
    async def _upgrade_lock(self, cursor: AsyncCursor, project_id: str, lock_id: str):
        # Upgrade an `ANALYSIS_READING` lock to `ANALYSIS_COMMITTING`

        async with self._advisory_lock(cursor, project_id):
            await cursor.execute(
                "SELECT COUNT(*) FROM locks WHERE project_id = %s AND lock_type = %s",
                (project_id, int(LockState.ARTIFACT)),
            )
            result = await _fetch_one(cursor)
            if result[0] == 0:
                lock_state = LockState.ANALYSIS_COMMITTING
            else:
                lock_state = LockState.ANALYSIS_PENDING_COMMIT

            await cursor.execute(
                "UPDATE locks SET lock_type = %s WHERE project_id = %s AND lock_id = %s",
                (int(lock_state), project_id, lock_id),
            )

        if lock_state == LockState.ANALYSIS_PENDING_COMMIT:
            await self._wait_lock(project_id, lock_id)

        try:
            yield None
        finally:
            async with self._advisory_lock(cursor, project_id):
                await cursor.execute(
                    "UPDATE locks SET lock_type = %s WHERE project_id = %s AND lock_id = %s",
                    (int(LockState.ANALYSIS_READING), project_id, lock_id),
                )

    async def make_lock(self, project_id: str, lock_type: LockRequest) -> str:
        async with self._cursor() as cursor:
            async with self._advisory_lock(cursor, project_id):
                lock_id = str(uuid.uuid4())
                if lock_type == LockRequest.ARTIFACT:
                    # See if we can already promote the lock
                    query = sql.SQL(
                        "SELECT COUNT(*) FROM locks WHERE "
                        "project_id = %s AND lock_type IN ({values})"
                    ).format(
                        values=_join_lockstates(
                            LockState.ANALYSIS_PENDING_COMMIT,
                            LockState.ANALYSIS_COMMITTING,
                        )
                    )
                    await cursor.execute(query, (project_id,))
                    if (await _fetch_one(cursor))[0] == 0:
                        lock_state = LockState.ARTIFACT
                    else:
                        lock_state = LockState.ARTIFACT_WAITING

                    await cursor.execute(
                        "INSERT INTO locks (project_id, lock_id, lock_type) VALUES (%s, %s, %s)",
                        (project_id, lock_id, int(lock_state)),
                    )

                elif lock_type == LockRequest.ANALYSIS:
                    query = sql.SQL(
                        "SELECT COUNT(*) FROM locks WHERE "
                        "project_id = %s AND lock_type IN ({values})"
                    ).format(
                        values=_join_lockstates(
                            LockState.ANALYSIS_READING,
                            LockState.ANALYSIS_PENDING_COMMIT,
                            LockState.ANALYSIS_COMMITTING,
                        )
                    )

                    await cursor.execute(query, (project_id,))
                    if (await _fetch_one(cursor))[0] == 0:
                        lock_state = LockState.ANALYSIS_READING
                    else:
                        lock_state = LockState.ANALYSIS_WAITING

                    await cursor.execute(
                        "INSERT INTO locks (project_id, lock_id, lock_type) VALUES (%s, %s, %s)",
                        (project_id, lock_id, int(lock_state)),
                    )

                else:
                    raise ValueError

            if lock_state in (LockState.ARTIFACT_WAITING, LockState.ANALYSIS_WAITING):
                await self._wait_lock(project_id, lock_id)
            return lock_id

    async def _unlock_next(self, project_id: str):
        pending_locks = await self._get_pending_locks(project_id)
        state = await self._compute_project_state(project_id)

        to_promote: list[tuple[str, LockState]] = []
        for lock_id, lock_state in pending_locks:
            if state.analysis_state == AnalysisState.WRITING and state.artifact_running:
                break

            if lock_state == LockState.ARTIFACT_WAITING:
                if state.analysis_state != AnalysisState.WRITING:
                    to_promote.append((lock_id, LockState.ARTIFACT))
                    state.artifact_running = True

            elif lock_state == LockState.ANALYSIS_WAITING:
                if state.analysis_state == AnalysisState.NONE:
                    to_promote.append((lock_id, LockState.ANALYSIS_READING))
                    state.analysis_state = AnalysisState.READING

            elif lock_state == LockState.ANALYSIS_PENDING_COMMIT:  # noqa: SIM102
                if not state.artifact_running:
                    to_promote.append((lock_id, LockState.ANALYSIS_COMMITTING))
                    state.analysis_state = AnalysisState.WRITING

        async with self._connection() as connection:
            for lock_id, new_state in to_promote:
                async with connection.transaction():
                    await connection.execute(
                        "UPDATE locks SET lock_type = %s WHERE project_id = %s AND lock_id = %s",
                        (int(new_state), project_id, lock_id),
                    )
                    await connection.execute(
                        sql.SQL("NOTIFY {}").format(sql.Identifier(f"lock_{project_id}_{lock_id}"))
                    )

    async def _delete_lock(self, cursor: AsyncCursor, project_id: str, lock_id: str):
        async with self._advisory_lock(cursor, project_id):
            await cursor.execute(
                "DELETE FROM locks WHERE project_id = %s AND lock_id = %s",
                (project_id, lock_id),
            )
            await self._unlock_next(project_id)

    async def _check_lock(
        self, cursor: AsyncCursor, project_id: str, lock_id: str, type_: LockCheckType
    ) -> CheckLockResult:
        if type_ == LockCheckType.NONE:
            return CheckLockResult.OK

        await cursor.execute(
            "SELECT refresh_timestamp + make_interval(secs => %s) > NOW(), lock_type"
            " FROM locks WHERE project_id = %s AND lock_id = %s",
            (LOCK_EXPIRY_SECONDS, project_id, lock_id),
        )
        result = await cursor.fetchone()
        if result is None:
            return CheckLockResult.MISSING
        if not result[0]:
            return CheckLockResult.EXPIRED

        actual_lock_type = result[1]
        if type_ == LockCheckType.ANY:
            return CheckLockResult.OK
        elif type_ == LockCheckType.ARTIFACT:
            ok = actual_lock_type in (
                int(LockState.ARTIFACT),
                int(LockState.ANALYSIS_READING),
                int(LockState.ANALYSIS_COMMITTING),
            )
        elif type_ == LockCheckType.ANALYSIS:
            ok = actual_lock_type in (
                int(LockState.ANALYSIS_READING),
                int(LockState.ANALYSIS_COMMITTING),
            )

        return CheckLockResult.OK if ok else CheckLockResult.TYPE_MISMATCH

    async def check_lock(self, project_id: str, lock_id: str, type_: LockCheckType) -> bool:
        async with self._cursor() as cursor:
            return (
                await self._check_lock(cursor, project_id, lock_id, type_)
            ) == CheckLockResult.OK

    async def renew_lock(self, project_id: str, lock_id: str):
        async with self._cursor() as cursor:
            state = await self._check_lock(cursor, project_id, lock_id, LockCheckType.ANY)
            if state == CheckLockResult.MISSING:
                return False
            elif state == CheckLockResult.EXPIRED:
                await self._delete_lock(cursor, project_id, lock_id)
                return False

            await cursor.execute(
                "UPDATE locks SET refresh_timestamp = NOW() WHERE project_id = %s AND lock_id = %s",
                (project_id, lock_id),
            )
            return True

    async def release_lock(self, project_id: str, lock_id: str):
        async with self._cursor() as cursor:
            await self._delete_lock(cursor, project_id, lock_id)

    async def _get_pending_locks(self, project_id: str) -> list[tuple[str, LockState]]:
        query = sql.SQL(
            "SELECT lock_id, lock_type FROM locks WHERE "
            "project_id = %s AND lock_type IN ({values}) ORDER BY creation_timestamp ASC"
        ).format(
            values=_join_lockstates(
                LockState.ARTIFACT_WAITING,
                LockState.ANALYSIS_WAITING,
                LockState.ANALYSIS_PENDING_COMMIT,
            )
        )

        async with self._cursor() as cursor:
            await cursor.execute(query, (project_id,))
            return await _row_generator(cursor, lambda r: (r[0], LockState[r[1]]))

    async def _compute_project_state(self, project_id: str) -> ProjectState:
        async with self._cursor() as cursor:
            await cursor.execute(
                sql.SQL(
                    "SELECT lock_type FROM locks WHERE project_id = %s "
                    "AND lock_type IN ({values}) LIMIT 1"
                ).format(
                    values=_join_lockstates(
                        LockState.ANALYSIS_READING,
                        LockState.ANALYSIS_PENDING_COMMIT,
                        LockState.ANALYSIS_COMMITTING,
                    )
                ),
                (project_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                analysis_state = AnalysisState.NONE
            else:
                lt = LockState(row[0])
                if lt == LockState.ANALYSIS_READING:
                    analysis_state = AnalysisState.READING
                else:
                    analysis_state = AnalysisState.WRITING

            await cursor.execute(
                "SELECT 1 FROM locks WHERE project_id = %s AND lock_type = %s LIMIT 1",
                (project_id, int(LockState.ARTIFACT)),
            )
            artifact_running = (await cursor.fetchone()) is not None

            return ProjectState(
                artifact_running=artifact_running,
                analysis_state=analysis_state,
            )

    async def _cleanup_locks(self):
        while True:
            await asyncio.sleep(30)
            async with self._cursor() as cursor:
                await cursor.execute(
                    "DELETE FROM locks WHERE refresh_timestamp + make_interval(secs => %s) < NOW()"
                    " RETURNING project_id, lock_id",
                    (LOCK_EXPIRY_SECONDS,),
                )

                already_unblocked_projects: set[str] = set()
                async for row in cursor:
                    if row[0] in already_unblocked_projects:
                        continue

                    await self._unlock_next(row[0])
                    already_unblocked_projects.add(row[0])

    #
    # Pypeline-facing endpoints
    #

    async def has_objects(
        self,
        project_id: str,
        savepoint_id: int,
        container_id: str,
        configuration_hash: str,
        object_ids: list[bytes],
    ) -> list[bytes]:
        if not object_ids:
            return []

        async with self._cursor() as cursor:
            await cursor.execute(
                "SELECT object_id FROM objects WHERE project_id = %s AND savepoint_id = %s "
                "AND container_id = %s AND configuration_hash = %s AND object_id = ANY(%s)",
                (project_id, savepoint_id, container_id, configuration_hash, object_ids),
            )
            return await _row_generator(cursor, lambda r: r[0])

    async def get_objects(
        self,
        project_id: str,
        savepoint_id: int,
        container_id: str,
        configuration_hash: str,
        object_ids: list[bytes],
    ) -> list[tuple[bytes, bytes]]:
        if not object_ids:
            return []

        async with self._cursor() as cursor:
            await cursor.execute(
                "SELECT object_id, content FROM objects "
                "WHERE project_id = %s AND savepoint_id = %s AND container_id = %s "
                "AND configuration_hash = %s AND object_id = ANY(%s)",
                (project_id, savepoint_id, container_id, configuration_hash, object_ids),
            )
            result = await _row_generator(cursor, lambda r: (r[0], r[1]))
            await cursor.execute(
                "UPDATE project SET last_fetch = NOW() WHERE project_id = %s",
                (project_id,),
            )
            return result

    async def get_custom_invalidation_data(
        self,
        project_id: str,
        pipe_id: int,
        configuration_hash: str,
    ) -> list[CustomDependencyEntry]:
        async with self._cursor() as cursor:
            await cursor.execute(
                "SELECT argument_index, object_id, data FROM custom_dependencies "
                "WHERE project_id = %s AND pipe_id = %s AND configuration_hash = %s",
                (project_id, pipe_id, configuration_hash),
            )
            return await _row_generator(cursor, lambda r: CustomDependencyEntry(r[0], r[1], r[2]))

    async def _run_invalidation(
        self,
        cursor: AsyncCursor,
        project_id: str,
        model_paths: list[str],
        additional_objects: list[AdditionalObjectEntry],
    ) -> list[InvalidatedObject]:
        if not model_paths and not additional_objects:
            return []

        suffix = uuid.uuid4().hex

        # Step 1, create the temporary tables
        await cursor.execute(INVALIDATE_CREATE_TABLES.format(suffix=suffix).encode())

        # Step 2, insert the incoming data
        if len(model_paths) > 0:
            await cursor.executemany(
                f"INSERT INTO model_paths_{suffix} VALUES (%s)".encode(),
                [(p,) for p in model_paths],
            )

        if len(additional_objects) > 0:
            await cursor.executemany(
                f"INSERT INTO additional_objects_{suffix} VALUES (%s, %s, %s, %s, %s)".encode(),
                (
                    (
                        ao.savepoint_id_start,
                        ao.savepoint_id_end,
                        ao.container_id,
                        ao.configuration_hash,
                        ao.object_id,
                    )
                    for ao in additional_objects
                ),
            )

        # Step 3, find the objects to delete, store them into
        # `invalidated_objects_<suffix>`
        await cursor.execute(
            INVALIDATE_FIND.format(suffix=suffix, objectid_mask=_OBJECTID_MASK).encode(),
            (project_id, project_id),
        )

        # Step 4, delete the dependencies for all the objects that are going to
        # be deleted
        await cursor.execute(INVALIDATE_DELETE_DEPENDENCIES.format(suffix=suffix).encode())

        # Step 5, actually delete the objects and return the invalidated data
        await cursor.execute(INVALIDATE_DELETE_OBJECTS.format(suffix=suffix).encode())
        return await _row_generator(
            cursor,
            lambda r: InvalidatedObject(
                object_id=r[0],
                container_id=r[1],
                savepoint_id=r[2],
                configuration_hash=r[3],
            ),
        )

    async def prune_objects(self, project_id: str):
        async with self._cursor() as cursor:
            await cursor.execute("DELETE FROM objects WHERE project_id = %s", (project_id,))
            await cursor.execute("DELETE FROM dependencies WHERE project_id = %s", (project_id,))
            await cursor.execute(
                "DELETE FROM custom_dependencies WHERE project_id = %s", (project_id,)
            )

    async def get_epoch(self, project_id: str) -> int:
        async with self._cursor() as cursor:
            await cursor.execute("SELECT epoch FROM project WHERE project_id = %s", (project_id,))
            row = await cursor.fetchone()
            assert row is not None
            return row[0]

    async def get_model(self, project_id: str) -> tuple[bytes | None, int]:
        async with self._cursor() as cursor:
            await cursor.execute(
                "SELECT model, epoch FROM project WHERE project_id = %s", (project_id,)
            )
            row = await cursor.fetchone()
            assert row is not None
            model = bytes(row[0]) if row[0] is not None else None
            return (model, row[1])

    async def add_objects(
        self,
        project_id: str,
        dependencies: list[DependencyEntry],
        custom_dependencies: list[CustomDependency],
        objects: list[ObjectEntry],
    ):
        async with self._cursor() as cursor:
            if len(dependencies) > 0:
                await cursor.executemany(
                    "INSERT INTO dependencies "
                    "(project_id, savepoint_id_start, savepoint_id_end, container_id, "
                    " configuration_hash, object_id, model_path)"
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (
                        (
                            project_id,
                            d.savepoint_id_start,
                            d.savepoint_id_end,
                            d.container_id,
                            d.configuration_hash,
                            d.object_id,
                            d.model_path,
                        )
                        for d in dependencies
                    ),
                )

            if custom_dependencies:
                await cursor.executemany(
                    "INSERT INTO custom_dependencies"
                    "(project_id, pipe_id, configuration_hash, argument_index, object_id, data) "
                    "VALUES (%s, %s, %s, %s, %s, %s)"
                    "ON CONFLICT (project_id, pipe_id, configuration_hash, argument_index, "
                    "  object_id) DO UPDATE SET data = EXCLUDED.data",
                    (
                        (
                            project_id,
                            cd.pipe_id,
                            cd.configuration_hash,
                            cd.argument_index,
                            cd.object_id,
                            cd.data,
                        )
                        for cd in custom_dependencies
                    ),
                )

            await cursor.executemany(
                "INSERT INTO objects "
                "(project_id, savepoint_id, container_id, configuration_hash, object_id, "
                "object_id_string, content) VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (project_id, savepoint_id, container_id, configuration_hash, "
                "  object_id) DO UPDATE SET content = EXCLUDED.content",
                (
                    (
                        project_id,
                        o.savepoint_id,
                        o.container_id,
                        o.configuration_hash,
                        o.object_id,
                        o.object_id_string,
                        o.content,
                    )
                    for o in objects
                ),
            )

            await cursor.execute(
                "UPDATE project SET last_object_save = NOW() WHERE project_id = %s",
                (project_id,),
            )

    async def invalidate_and_set_model(
        self,
        project_id: str,
        lock_id: str,
        model_paths: list[str],
        additional_objects: list[AdditionalObjectEntry],
        model_bytes: bytes,
    ) -> ModelSetResult:
        async with self._cursor() as cursor:
            async with self._upgrade_lock(cursor, project_id, lock_id):
                invalidated_rows = await self._run_invalidation(
                    cursor, project_id, model_paths, additional_objects
                )

                await cursor.execute(
                    "UPDATE project SET model = %s, epoch = epoch + 1, last_model_save = NOW()"
                    " WHERE project_id = %s RETURNING epoch",
                    (model_bytes, project_id),
                )
                row = await cursor.fetchone()
                assert row is not None

            return ModelSetResult(new_epoch=row[0], invalidated=invalidated_rows)

    async def get_metadata(self, project_id: str) -> ProjectMetadataRow:
        async with self._cursor() as cursor:
            await cursor.execute(
                "SELECT pipeline_description_hash, version, "
                "extract(epoch FROM last_fetch)::float AS last_fetch, "
                "extract(epoch FROM last_object_save)::float AS last_object_save, "
                "extract(epoch FROM last_model_save)::float AS last_model_save "
                "FROM project WHERE project_id = %s",
                (project_id,),
            )

            cursor.row_factory = cast(Any, dict_row)
            row = cast(DictRow, await _fetch_one(cursor))
            return cast(ProjectMetadataRow, row)

    async def create_project_if_missing(self, project_id: str):
        async with self._cursor() as cursor:
            await cursor.execute(
                "INSERT INTO project (project_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (project_id,),
            )

    async def check_metadata(
        self, project_id: str, version: str, pipeline_description_hash: str
    ) -> CheckMetadataResult:
        async with self._cursor() as cursor:
            await cursor.execute(
                "SELECT version, pipeline_description_hash FROM project WHERE project_id = %s",
                (project_id,),
            )
            result = await _fetch_one(cursor)

            if result[0] == version and result[1] == pipeline_description_hash:
                return CheckMetadataResult.OK

            # Check that the pipeline description hash is present, otherwise do
            # an early return
            if result[1] != pipeline_description_hash:
                await cursor.execute(
                    "SELECT 1 FROM pipeline_descriptions WHERE hash = %s",
                    (pipeline_description_hash,),
                )
                if (await cursor.fetchone()) is None:
                    return CheckMetadataResult.PIPELINE_DESCRTION_HASH_MISSING

            # If we're here we need to prune everything, first obtain an
            # analysis lock in the committing state
            lock_id = await self.make_lock(project_id, LockRequest.ANALYSIS)
            async with self._upgrade_lock(cursor, project_id, lock_id):
                await self.prune_objects(project_id)
                await cursor.execute(
                    "UPDATE project SET version = %s, pipeline_description_hash = %s, "
                    "last_object_save = NOW() WHERE project_id = %s",
                    (version, pipeline_description_hash, project_id),
                )
            await self._delete_lock(cursor, project_id, lock_id)

            return CheckMetadataResult.PRUNE_DONE

    async def put_pipeline_description(self, project_id: str, hash_: str, content: bytes):
        async with self._cursor() as cursor:
            await cursor.execute(
                "INSERT INTO pipeline_descriptions (hash, content) VALUES (%s, %s)"
                "ON CONFLICT (hash) DO NOTHING",
                (hash_, content),
            )

    async def put_file(self, project_id: str, hash_: str, content: bytes):
        async with self._cursor() as cursor:
            # Check if the file has already been uploaded, this saves us from
            # shipping the (possibly big) binary over to the DB
            await cursor.execute(
                "SELECT 1 FROM file_storage WHERE project_id = %s and hash = %s",
                (project_id, hash_),
            )
            if (await cursor.fetchone()) is not None:
                return

            await cursor.execute(
                "INSERT INTO file_storage (project_id, hash, content) VALUES (%s, %s, %s)"
                "ON CONFLICT (project_id, hash) DO NOTHING",
                (project_id, hash_, content),
            )

    async def get_files(self, project_id: str, hashes: list[str]) -> dict[str, bytes]:
        if len(hashes) == 0:
            return {}

        async with self._cursor() as cursor:
            await cursor.execute(
                "SELECT hash, content FROM file_storage WHERE project_id = %s AND hash = ANY(%s)",
                (project_id, hashes),
            )
            result = {}
            async for row in cursor:
                result[row[0]] = bytes(row[1])
            return result
