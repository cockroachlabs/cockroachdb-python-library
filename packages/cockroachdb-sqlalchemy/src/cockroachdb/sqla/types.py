"""CockroachDB type mapping for SQLAlchemy.

Maps CockroachDB type names (as returned by ``information_schema.columns``)
to SQLAlchemy type objects.  This is used by :class:`CockroachDBDialect` for
column reflection.
"""

from __future__ import annotations

import sqlalchemy.types as sqltypes
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID

CRDB_TYPE_MAP: dict[str, sqltypes.TypeEngine] = {
    "bool": sqltypes.Boolean(),
    "boolean": sqltypes.Boolean(),
    "bigint": sqltypes.BigInteger(),
    "int": sqltypes.Integer(),
    "int2": sqltypes.SmallInteger(),
    "int4": sqltypes.Integer(),
    "int8": sqltypes.BigInteger(),
    "int64": sqltypes.BigInteger(),
    "integer": sqltypes.Integer(),
    "smallint": sqltypes.SmallInteger(),
    "double precision": sqltypes.Float(),
    "float": sqltypes.Float(),
    "float4": sqltypes.Float(),
    "float8": sqltypes.Float(),
    "real": sqltypes.Float(),
    "dec": sqltypes.Numeric(),
    "decimal": sqltypes.Numeric(),
    "numeric": sqltypes.Numeric(),
    "date": sqltypes.Date(),
    "time": sqltypes.Time(),
    "time without time zone": sqltypes.Time(),
    "timestamp": sqltypes.DateTime(),
    "timestamptz": sqltypes.DateTime(timezone=True),
    "timestamp with time zone": sqltypes.DateTime(timezone=True),
    "timestamp without time zone": sqltypes.DateTime(),
    "interval": sqltypes.Interval(),
    "char": sqltypes.CHAR(),
    "character": sqltypes.CHAR(),
    "character varying": sqltypes.String(),
    "string": sqltypes.String(),
    "text": sqltypes.Text(),
    "varchar": sqltypes.String(),
    "blob": sqltypes.LargeBinary(),
    "bytea": sqltypes.LargeBinary(),
    "bytes": sqltypes.LargeBinary(),
    "json": sqltypes.JSON(),
    "jsonb": JSONB(),
    "uuid": UUID(),
    "inet": INET(),
}


def resolve_type(type_str: str) -> sqltypes.TypeEngine:
    """Resolve a CockroachDB type string to a SQLAlchemy type.

    Handles parameterized types like ``VARCHAR(255)`` and ``DECIMAL(10,2)``.
    Falls back to :data:`sqltypes.NULLTYPE` for unrecognised types.
    """
    import re

    if not type_str:
        return sqltypes.NULLTYPE

    type_str = type_str.strip().lower()

    if type_str.endswith("[]"):
        base = resolve_type(type_str[:-2])
        return ARRAY(type(base))

    m = re.match(r"^([a-z_ ]+?)(?:\((.+)\))?$", type_str)
    if not m:
        return sqltypes.NULLTYPE

    type_name = m.group(1).strip()
    type_args = m.group(2)

    if type_name in CRDB_TYPE_MAP:
        if type_args:
            type_class = type(CRDB_TYPE_MAP[type_name])
            args = [int(a.strip()) for a in type_args.split(",")]
            return type_class(*args)
        return CRDB_TYPE_MAP[type_name]

    return sqltypes.NULLTYPE
