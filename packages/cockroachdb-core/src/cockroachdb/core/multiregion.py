"""Multi-region schema check — shared introspection, compare, and fix-up SQL.

A faithful port of the Spring starter's startup check
(``com.cockroachlabs.data.multiregion.MultiregionCheck``). It compares what a
model declares (``GLOBAL`` / ``REGIONAL BY ROW``) against the live multi-region
configuration of its database and tables, and suggests SQL for every
difference. It only ever reads; it never changes the schema.

The surfaces (SQLAlchemy ``verify_multiregion_schema`` and the Django system
check) enumerate their models into :class:`MultiregionTable` records, hand this
module a ``query`` callable, and act on the returned :class:`MultiregionReport`.

Modes (``none`` | ``warn`` | ``validate``, default ``warn``):

* ``none`` — skip entirely.
* ``warn`` — report problems, but a **contradiction** (an annotation naming one
  locality while the table has the other, or annotations that disagree) still
  fails: the model and the schema disagree about where rows live, so one is
  wrong.
* ``validate`` — any problem fails.

All queries use ``SHOW`` statements and ``information_schema``, never
``crdb_internal`` (recent CockroachDB versions restrict it by default).
Identifiers that collide with reserved/type keywords are quoted
(``pg_get_keywords()``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

NONE = "none"
WARN = "warn"
VALIDATE = "validate"
_MODES = (NONE, WARN, VALIDATE)

_REGION_TYPE = "crdb_internal_region"
_IMPLICIT_REGION_COLUMN = "crdb_region"
_REGIONAL_BY_ROW = "REGIONAL BY ROW"
_CONTRADICTION = "Contradiction: "
_SOURCE = "cockroachdb.core.multiregion"
_OVERVIEW = "https://docs.cockroachlabs.com/docs/stable/multiregion-overview"

_PLAIN_RE = re.compile(r"[a-z_][a-z0-9_$]*")


class Query(Protocol):
    """A function that runs ``sql`` with positional ``%s`` params and returns rows."""

    def __call__(self, sql: str, params: Sequence[object] = ()) -> list[tuple[Any, ...]]: ...


def normalize_mode(mode: str) -> str:
    """Lower-cased, validated mode. Fails fast on an unknown value."""
    normalized = (mode or "").strip().lower()
    if normalized not in _MODES:
        raise ValueError(f"multiregion mode must be one of {_MODES}, got {mode!r}")
    return normalized


class MultiregionCheckError(Exception):
    """Raised when the multi-region check fails (validate mode, or a contradiction)."""


class Kind(Enum):
    """What a model's annotations expect of its table."""

    NONE = "NONE"
    GLOBAL = "GLOBAL"
    REGIONAL_BY_ROW = "REGIONAL_BY_ROW"
    BOTH = "BOTH"


def kind_for(locality: str | None) -> Kind:
    """Maps a declared locality string (from a mixin) to a :class:`Kind`."""
    if locality == "GLOBAL":
        return Kind.GLOBAL
    if locality == _REGIONAL_BY_ROW:
        return Kind.REGIONAL_BY_ROW
    return Kind.NONE


@dataclass(frozen=True)
class MultiregionTable:
    """A model's table and what its locality declaration, if any, expects.

    Names are as CockroachDB stores them (unquoted names fold to lower case).

    Args:
        entity: the model's name, for messages (so it can be found in an IDE).
        table: the table's name.
        kind: what the declaration expects; :attr:`Kind.NONE` for neither.
        schema: the table's schema, or ``None`` for the connection's current schema.
        region_column: the REGIONAL BY ROW region column, or ``None`` for the implicit
            ``crdb_region``.
    """

    entity: str
    table: str
    kind: Kind = Kind.NONE
    schema: str | None = None
    region_column: str | None = None


@dataclass(frozen=True)
class TableInfo:
    locality: str | None
    column_types: dict[str, str] = field(default_factory=dict)


@dataclass
class MultiregionState:
    database: str
    current_schema: str
    primary_region: str | None
    cluster_regions: list[str]
    tables: dict[tuple[str, str], TableInfo]
    keywords: set[str]


class MultiregionReport:
    """The problems the check found and SQL that fixes them."""

    def __init__(self) -> None:
        self.problems: list[str] = []
        self.statements: list[str] = []
        self.contradictions = 0

    def problem(self, text: str) -> None:
        self.problems.append(text)

    def contradiction(self, text: str) -> None:
        self.problems.append(_CONTRADICTION + text)
        self.contradictions += 1

    def statement(self, text: str) -> None:
        self.statements.append(text)

    def is_empty(self) -> bool:
        return not self.problems

    def has_contradictions(self) -> bool:
        return self.contradictions > 0

    def format(self, mode: str, *, setting: str = "multiregion mode") -> str:
        """The report as one message, naming its source and the mode that decided it."""
        count = len(self.problems)
        out = [
            f"CockroachDB multiregion check ({_SOURCE}, {setting}={mode}) found "
            f"{count} {'problem' if count == 1 else 'problems'}:"
        ]
        for problem in self.problems:
            out.append("  - " + problem.replace("\n", "\n    "))
        if self.contradictions:
            out.append(
                "\nContradictions stop the check in every mode but none: the annotations"
                " and the schema disagree about where rows live, so one of them is wrong."
            )
        if self.statements:
            out.append("\nSuggested SQL (review, then add to a migration; or alter the model):")
            out.extend("  " + statement for statement in self.statements)
        out.append("\nSee also: " + _OVERVIEW)
        return "\n".join(out)


def check_outcome(mode: str, report: MultiregionReport) -> str:
    """The decision for a report: ``"ok"`` | ``"warn"`` | ``"fail"``.

    A contradiction fails even in warn mode — this is the single place that rule
    lives, so a regression here flips exactly one unit test.
    """
    if report.is_empty():
        return "ok"
    if mode == VALIDATE or report.has_contradictions():
        return "fail"
    return "warn"


# --- identifiers -----------------------------------------------------------


def parse_identifier(rendered: str) -> list[str]:
    """Splits a qualified, possibly quoted name (``app."Orders"``) into its parts."""
    parts: list[str] = []
    part: list[str] = []
    in_quotes = False
    quoted = False
    i = 0
    n = len(rendered)
    while i < n:
        c = rendered[i]
        if in_quotes:
            if c != '"':
                part.append(c)
            elif i + 1 < n and rendered[i + 1] == '"':
                part.append('"')
                i += 1
            else:
                in_quotes = False
        elif c == '"':
            in_quotes = True
            quoted = True
        elif c == ".":
            parts.append(_finish(part, quoted))
            part = []
            quoted = False
        else:
            part.append(c)
        i += 1
    parts.append(_finish(part, quoted))
    return parts


def _finish(part: list[str], quoted: bool) -> str:
    name = "".join(part)
    return name if quoted else name.strip().lower()


def quote_identifier(name: str, keywords: set[str]) -> str:
    """Quotes ``name`` unless it is a plain identifier that is not a keyword."""
    if _PLAIN_RE.fullmatch(name) and name not in keywords:
        return name
    return '"' + name.replace('"', '""') + '"'


def _region_literal(region: str) -> str:
    return '"' + region.replace('"', '""') + '"'


def regional_by_row_column(locality: str | None) -> str | None:
    """The region column of a ``REGIONAL BY ROW`` locality, or ``None`` otherwise."""
    if locality is None or not locality.startswith(_REGIONAL_BY_ROW):
        return None
    rest = locality[len(_REGIONAL_BY_ROW) :].strip()
    if not rest:
        return _IMPLICIT_REGION_COLUMN
    if rest.startswith("AS "):
        return parse_identifier(rest[3:].strip())[0]
    return None


def _is_region_type(type_name: str) -> bool:
    return type_name == _REGION_TYPE or type_name.endswith("." + _REGION_TYPE)


def _name_of(table: MultiregionTable, current_schema: str) -> tuple[str, str]:
    return (table.schema if table.schema is not None else current_schema, table.table)


# --- introspection ---------------------------------------------------------


def is_cockroachdb(query: Query) -> bool:
    """Whether the connection behind ``query`` is to CockroachDB."""
    try:
        rows = query("SELECT version()")
        return bool(rows) and rows[0][0] is not None and "CockroachDB" in rows[0][0]
    except Exception:
        return False


def load_state(query: Query, tables: list[MultiregionTable]) -> MultiregionState:
    """Reads what :func:`evaluate` needs for ``tables``."""
    row = query("SELECT current_database(), current_schema()")[0]
    database = row[0]
    current_schema = row[1] if row[1] is not None else "public"

    primary_region = None
    primary_rows = query(
        "SELECT primary_region FROM [SHOW DATABASES] WHERE database_name = %s", (database,)
    )
    if primary_rows:
        primary_region = primary_rows[0][0]

    cluster_regions = [
        r[0] for r in query("SELECT region FROM [SHOW REGIONS FROM CLUSTER] ORDER BY region")
    ]

    keywords = {
        r[0] for r in query("SELECT word FROM pg_get_keywords() WHERE catcode IN ('R', 'T')")
    }

    wanted = {_name_of(t, current_schema) for t in tables}
    found: dict[tuple[str, str], TableInfo] = {}
    for r in query(
        "SELECT schema_name, table_name, locality FROM [SHOW TABLES] WHERE type = 'table'"
    ):
        name = (r[0], r[1])
        if name in wanted:
            found[name] = TableInfo(r[2])

    for table in tables:
        name = _name_of(table, current_schema)
        info = found.get(name)
        if table.kind == Kind.REGIONAL_BY_ROW and info is not None:
            found[name] = TableInfo(info.locality, _column_types(query, name))

    return MultiregionState(
        database, current_schema, primary_region, cluster_regions, found, keywords
    )


def _column_types(query: Query, name: tuple[str, str]) -> dict[str, str]:
    rows = query(
        "SELECT column_name, crdb_sql_type FROM information_schema.columns "
        "WHERE table_catalog = current_database() AND table_schema = %s AND table_name = %s",
        (name[0], name[1]),
    )
    return {r[0]: r[1] for r in rows}


# --- compare ---------------------------------------------------------------


def evaluate(state: MultiregionState, tables: list[MultiregionTable]) -> MultiregionReport:
    """Every difference between ``tables`` and ``state``, with SQL to fix the schema."""
    report = MultiregionReport()
    keywords = state.keywords
    multiregion = state.primary_region is not None
    annotated = [t for t in tables if t.kind != Kind.NONE]

    if not multiregion and annotated:
        database = quote_identifier(state.database, keywords)
        names = ", ".join(t.entity for t in annotated)
        n = len(annotated)
        affected = (
            f"GLOBAL/REGIONAL BY ROW declarations on {n} "
            f"{'entity' if n == 1 else 'entities'} ({names}) have no effect."
        )
        if not state.cluster_regions:
            report.problem(
                f"Database {database} is not multi-region; {affected}\n"
                "The cluster has no regions, so the database can't be made multi-region yet:"
                " start every node with --locality=region=<region>."
            )
        else:
            report.problem(
                f"Database {database} is not multi-region; {affected}\n"
                f"The cluster has regions: {', '.join(state.cluster_regions)}."
                " Choose the primary region deliberately; the SQL below uses the first one."
            )
            regions = state.cluster_regions
            report.statement(
                f"ALTER DATABASE {database} SET PRIMARY REGION {_region_literal(regions[0])};"
            )
            for region in regions[1:]:
                report.statement(
                    f"ALTER DATABASE {database} ADD REGION {_region_literal(region)};"
                )

    by_table: dict[tuple[str, str], list[MultiregionTable]] = {}
    for table in tables:
        by_table.setdefault(_name_of(table, state.current_schema), []).append(table)

    for name, entities in by_table.items():
        qualified = quote_identifier(name[0], keywords) + "." + quote_identifier(name[1], keywords)
        info = state.tables.get(name)
        annotated_entities = [t for t in entities if t.kind != Kind.NONE]
        kinds = {t.kind for t in annotated_entities}

        if not kinds:
            _unannotated(report, qualified, info, entities, multiregion)
        elif len(kinds) > 1 or Kind.BOTH in kinds:
            _conflicting(report, qualified, annotated_entities)
        else:
            table = annotated_entities[0]
            if table.kind == Kind.GLOBAL:
                _global(report, qualified, info, table, multiregion)
            else:
                _regional_by_row(report, state, table, qualified, info, multiregion)
    return report


def _global(
    report: MultiregionReport,
    qualified: str,
    info: TableInfo | None,
    table: MultiregionTable,
    multiregion: bool,
) -> None:
    if info is None:
        _missing(report, qualified, "@GlobalTable", table)
    elif not multiregion or info.locality != "GLOBAL":
        if multiregion:
            problem = (
                f"Table {qualified} (@GlobalTable {table.entity}) is {info.locality}, not GLOBAL."
            )
            if regional_by_row_column(info.locality) is not None:
                report.contradiction(problem)
            else:
                report.problem(problem)
        report.statement(f"ALTER TABLE {qualified} SET LOCALITY GLOBAL;")


def _unannotated(
    report: MultiregionReport,
    qualified: str,
    info: TableInfo | None,
    entities: list[MultiregionTable],
    multiregion: bool,
) -> None:
    if info is None or not multiregion:
        return
    names = ", ".join(t.entity for t in entities)
    if info.locality == "GLOBAL":
        report.problem(
            f"Table {qualified} is GLOBAL, but entity {names} has no @GlobalTable. "
            "Add the GlobalTableMixin to it."
        )
    elif (column := regional_by_row_column(info.locality)) is not None:
        report.problem(
            f"Table {qualified} is {info.locality}, but entity {names} has no @RegionalByRow. "
            f"Add the RegionalByRowMixin to it, with a {column} column so rows are homed in the"
            " transaction's region."
        )


def _conflicting(
    report: MultiregionReport, qualified: str, entities: list[MultiregionTable]
) -> None:
    if len(entities) == 1:
        report.contradiction(
            f"Entity {entities[0].entity} declares both GLOBAL and REGIONAL BY ROW; keep one."
        )
        return
    described = ", ".join(
        f"{t.entity} ("
        + {
            Kind.GLOBAL: "GLOBAL",
            Kind.REGIONAL_BY_ROW: "REGIONAL BY ROW",
        }.get(t.kind, "GLOBAL and REGIONAL BY ROW")
        + ")"
        for t in entities
    )
    report.contradiction(
        f"Table {qualified} is mapped by entities with conflicting declarations: "
        f"{described}. Declare them alike."
    )


def _regional_by_row(
    report: MultiregionReport,
    state: MultiregionState,
    table: MultiregionTable,
    qualified: str,
    info: TableInfo | None,
    multiregion: bool,
) -> None:
    if info is None:
        _missing(report, qualified, "@RegionalByRow", table)
        return
    wanted_column = table.region_column
    current_column = regional_by_row_column(info.locality)
    if (
        multiregion
        and current_column is not None
        and (wanted_column is None or wanted_column == current_column)
    ):
        return

    column = wanted_column if wanted_column is not None else _IMPLICIT_REGION_COLUMN
    quoted_column = quote_identifier(column, state.keywords)
    col_type = info.column_types.get(column)
    description = f"Table {qualified} (@RegionalByRow {table.entity})"
    target = (
        _REGIONAL_BY_ROW
        if column == _IMPLICIT_REGION_COLUMN
        else f"{_REGIONAL_BY_ROW} AS {quoted_column}"
    )
    is_global = multiregion and info.locality == "GLOBAL"
    if is_global:
        report.contradiction(f"{description} is GLOBAL, not {target}.")
    if col_type is not None and not _is_region_type(col_type):
        report.problem(
            f"{description}: column {quoted_column} is {col_type}, but REGIONAL BY ROW needs a "
            f"{_REGION_TYPE} column. Change it with your migrations."
        )
        return
    if col_type is None and column != _IMPLICIT_REGION_COLUMN:
        report.problem(
            f"{description}: column {quoted_column} does not exist. Create it, as a "
            f"{_REGION_TYPE} column, with your migrations."
        )
        return

    if multiregion and not is_global:
        report.problem(f"{description} is {info.locality}, not {target}.")
    report.statement(f"ALTER TABLE {qualified} SET LOCALITY {target};  -- rewrites the table")


def _missing(
    report: MultiregionReport, qualified: str, annotation: str, table: MultiregionTable
) -> None:
    report.problem(
        f"Table {qualified} ({annotation} {table.entity}) does not exist. "
        "Create it with your migrations."
    )


def evaluate_schema(
    query: Query, tables: list[MultiregionTable], mode: str
) -> tuple[str, MultiregionReport | None]:
    """Orchestrates the read-only check.

    Returns ``(outcome, report)``. ``outcome`` is ``"skip"`` (mode none, or not
    CockroachDB), ``"ok"``, ``"warn"``, or ``"fail"``. Callers decide what to do
    with each outcome (log, raise, emit a Django ``CheckMessage``). This function
    never changes the schema and never raises for a failing comparison — it just
    reports the verdict.
    """
    mode = normalize_mode(mode)
    if mode == NONE or not tables or not is_cockroachdb(query):
        return ("skip", None)
    state = load_state(query, tables)
    report = evaluate(state, tables)
    return (check_outcome(mode, report), report)
