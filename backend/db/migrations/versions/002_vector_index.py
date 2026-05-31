"""add IVFFlat vector index on chunk_embeddings

Revision ID: 002
Revises: 001
Create Date: 2026-05-31

IVFFlat 인덱스는 데이터가 있어야 클러스터 중심점을 계산할 수 있다.
빈 테이블에 생성하면 경고 발생 → 파이프라인 첫 실행 완료 후 적용.
lists=175: ceil(sqrt(30000)) — 초기 3만 청크 기준 (docs/04-vector-schema.md 섹션 5-3)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # lists=175: ceil(sqrt(30000)) — docs/04-vector-schema.md 섹션 5-3 참고
    op.execute("""
        CREATE INDEX idx_chunk_embeddings_embedding_ivfflat
            ON chunk_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 175)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunk_embeddings_embedding_ivfflat")
