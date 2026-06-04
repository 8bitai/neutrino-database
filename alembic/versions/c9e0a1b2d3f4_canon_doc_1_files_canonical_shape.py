"""[NEU-1816] CANON-DOC-1 — files gains CanonicalDocument shape.

Unifies the `files` table so it can represent both file-source
connectors (SharePoint, OneDrive, Drive — bytes) AND record-source
connectors (Jira, Confluence, Slack, Linear — JSON records that have
no bytes). See product-feature-roadmap/enterprise-search/
unified-doc-parse-chunk.md (CanonicalDocument shape).

What changes:

  * NEW columns added to `files`:
      source_type, source_url, container_id, container_name,
      breadcrumb, language, parent_doc_id, facets, display_metadata,
      title, viewers, acl_extractor_version, acl_extracted_at
  * NEW enum `file_source_type` with the 12 canonical kinds.
  * NEW self-FK on `parent_doc_id` so deleting a parent issue/thread
    cascades comments / replies / attachments.
  * RELAXED to nullable (record-source rows leave them NULL):
      original_filename, file_type, storage_uri, file_size_bytes,
      file_sha256

Pre-production note (per [[project_pre_production_no_real_users]]) —
existing `files` rows all came from the file-upload path, so we
backfill `source_type='file'` via a server-default at column-add time.
The default sticks (so legacy upload code paths that don't specify
source_type continue to work); the explicit values from canonical
ingest are picked up via record-source connectors.

Revision ID: c9e0a1b2d3f4
Revises: 0f8c72b60508
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c9e0a1b2d3f4"
down_revision: str | None = "0f8c72b60508"
branch_labels = None
depends_on = None


# Closed vocabulary from unified-doc-parse-chunk.md "Source_type".
_SOURCE_TYPES = (
    "file",
    "issue",
    "pull_request",
    "commit",
    "page",
    "record",
    "message",
    "email",
    "event",
    "comment",
    "attachment",
    "ticket",
)


def upgrade() -> None:
    # ── 1. Create the file_source_type enum ──────────────────────────
    file_source_type = postgresql.ENUM(
        *_SOURCE_TYPES, name="file_source_type", create_type=False
    )
    file_source_type.create(op.get_bind(), checkfirst=True)

    # ── 2. Add CanonicalDocument columns to files ────────────────────
    op.add_column(
        "files",
        sa.Column(
            "source_type",
            postgresql.ENUM(
                *_SOURCE_TYPES, name="file_source_type", create_type=False
            ),
            nullable=False,
            server_default="file",
            comment=(
                "CanonicalDocument source kind (file / issue / page / "
                "message / …). Drives chunking regime + citation card "
                "+ ranking weights. Closed vocabulary."
            ),
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "source_url",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="Clickable link back to the source record.",
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "container_id",
            sa.String(255),
            nullable=False,
            server_default="",
            comment=(
                "Provider's container id — drive id / project key / "
                "space key / channel id / repo full_name."
            ),
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "container_name",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="Human-readable container name for citations.",
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "breadcrumb",
            postgresql.JSONB(),
            nullable=True,
            comment="Full parent chain, e.g. ['Site','Library','Folder'].",
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "language",
            sa.String(10),
            nullable=True,
            comment="ISO 639-1 code; detected if not provided by source.",
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "parent_doc_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment=(
                "Self-FK for comments/replies/attachments. Cascade on "
                "delete so removing a parent issue/thread removes its "
                "children."
            ),
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "facets",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment=(
                "Indexed-as-keyword filter bag. Provider names the keys "
                "(status, priority, assignee, …); chat agent + UI use "
                "them as facet filters."
            ),
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "display_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment=(
                "Display-only bag — surfaced in citation card 'View "
                "details' expand panel, never searched on. Named "
                "display_metadata to avoid SQLAlchemy MetaData clash."
            ),
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "title",
            sa.Text(),
            nullable=True,
            comment=(
                "Human title. Nullable: messages / commits have none — "
                "title_fallback (body excerpt) covers citation rendering "
                "in those cases."
            ),
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "viewers",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment=(
                "Serialized ViewerSet — source of truth for ACL. Drives "
                "both OpenFGA Store B tuples AND the denormalized "
                "acl_principals[] on every ES chunk. Default '{}' means "
                "default-deny on ACL-unresolved rows."
            ),
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "acl_extractor_version",
            sa.SmallInteger(),
            nullable=True,
            comment=(
                "Bumped on per-provider ACL extractor changes. A doc "
                "indexed with an older version forces re-resolve on "
                "next sync."
            ),
        ),
    )
    op.add_column(
        "files",
        sa.Column(
            "acl_extracted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="When the ViewerSet was resolved at sync time.",
        ),
    )

    # ── 3. Self-FK on parent_doc_id with CASCADE ─────────────────────
    op.create_foreign_key(
        "files_parent_doc_id_fkey",
        source_table="files",
        referent_table="files",
        local_cols=["parent_doc_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # Index for parent → children lookup (chat agent rebuilds threads).
    op.create_index(
        "ix_files_parent_doc_id",
        "files",
        ["parent_doc_id"],
        unique=False,
        postgresql_where=sa.text("parent_doc_id IS NOT NULL"),
    )

    # ── 4. Relax file-only NOT NULL constraints ──────────────────────
    # Record-source connectors (Jira, Confluence, …) have none of these:
    # they have title + body, not a filename + bytes.
    for col in (
        "original_filename",
        "file_type",
        "storage_uri",
        "file_size_bytes",
        "file_sha256",
    ):
        op.alter_column("files", col, nullable=True)


def downgrade() -> None:
    # ── Reverse: tighten file-only columns ──────────────────────────
    # WARNING: downgrade only safe in pre-production. Re-imposing NOT
    # NULL fails if any record-source rows exist (no filename / mime).
    for col in (
        "original_filename",
        "file_type",
        "storage_uri",
        "file_size_bytes",
        "file_sha256",
    ):
        op.alter_column("files", col, nullable=False)

    op.drop_index("ix_files_parent_doc_id", table_name="files")
    op.drop_constraint("files_parent_doc_id_fkey", "files", type_="foreignkey")

    for col in (
        "acl_extracted_at",
        "acl_extractor_version",
        "viewers",
        "title",
        "display_metadata",
        "facets",
        "parent_doc_id",
        "language",
        "breadcrumb",
        "container_name",
        "container_id",
        "source_url",
        "source_type",
    ):
        op.drop_column("files", col)

    postgresql.ENUM(name="file_source_type").drop(
        op.get_bind(), checkfirst=True
    )
