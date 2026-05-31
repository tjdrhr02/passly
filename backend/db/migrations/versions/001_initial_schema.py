"""initial schema: 16 tables + extensions + triggers + indexes

Revision ID: 001
Revises:
Create Date: 2026-05-31

docs/03-erd-physical.md 기준 전체 DDL.
실행 순서: 확장 → 함수 → 테이블(의존성 순) → B-tree 인덱스 → GIN 인덱스 → 트리거
IVFFlat 벡터 인덱스는 데이터 삽입 완료 후 별도 실행 권장 (002_vector_index.py)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────
    # 1. PostgreSQL 확장 설치
    # ──────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # ──────────────────────────────────────────────
    # 2. 공통 트리거 함수
    # ──────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # ──────────────────────────────────────────────
    # 3. 테이블 DDL (의존성 순서 준수)
    # ──────────────────────────────────────────────

    # 3-1. code_values
    op.execute("""
        CREATE TABLE code_values (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            code_group  VARCHAR(50) NOT NULL,
            code_value  VARCHAR(50) NOT NULL,
            code_name   VARCHAR(100) NOT NULL,
            sort_order  INTEGER     NOT NULL DEFAULT 0,
            is_active   BOOLEAN     NOT NULL DEFAULT true,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted  BOOLEAN     NOT NULL DEFAULT false,
            CONSTRAINT uq_code_values_group_value UNIQUE (code_group, code_value)
        )
    """)

    # 3-2. certifications
    op.execute("""
        CREATE TABLE certifications (
            id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            name             VARCHAR(255) NOT NULL,
            vendor           VARCHAR(100) NOT NULL,
            exam_code        VARCHAR(50)  NOT NULL UNIQUE,
            is_active        BOOLEAN      NOT NULL DEFAULT true,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            is_deleted       BOOLEAN      NOT NULL DEFAULT false
        )
    """)

    # 3-3. users
    op.execute("""
        CREATE TABLE users (
            id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            email          VARCHAR(255) NOT NULL UNIQUE,
            name           VARCHAR(255) NOT NULL,
            access_level   VARCHAR(50)  NOT NULL DEFAULT 'PRIVATE',
            last_login_at  TIMESTAMPTZ,
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            is_deleted     BOOLEAN      NOT NULL DEFAULT false
        )
    """)

    # 3-4. exam_domains
    op.execute("""
        CREATE TABLE exam_domains (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            certification_id  UUID        NOT NULL REFERENCES certifications(id) ON DELETE RESTRICT,
            name              VARCHAR(100) NOT NULL,
            weight_percent    INTEGER     NOT NULL CHECK (weight_percent BETWEEN 1 AND 100),
            order_num         INTEGER     NOT NULL,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted        BOOLEAN     NOT NULL DEFAULT false
        )
    """)

    # 3-5. topics
    op.execute("""
        CREATE TABLE topics (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            exam_domain_id  UUID         NOT NULL REFERENCES exam_domains(id) ON DELETE RESTRICT,
            name            VARCHAR(100) NOT NULL,
            description     TEXT,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
            is_deleted      BOOLEAN      NOT NULL DEFAULT false
        )
    """)

    # 3-6. learning_documents
    op.execute("""
        CREATE TABLE learning_documents (
            id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            certification_id  UUID         NOT NULL REFERENCES certifications(id) ON DELETE RESTRICT,
            title             VARCHAR(255) NOT NULL,
            source_type       VARCHAR(50)  NOT NULL,
            file_path         VARCHAR(500) NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            is_active         BOOLEAN      NOT NULL DEFAULT true,
            created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
            is_deleted        BOOLEAN      NOT NULL DEFAULT false
        )
    """)

    # 3-7. document_versions
    op.execute("""
        CREATE TABLE document_versions (
            id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            learning_document_id UUID        NOT NULL REFERENCES learning_documents(id) ON DELETE RESTRICT,
            version_number       INTEGER     NOT NULL DEFAULT 1,
            is_active            BOOLEAN     NOT NULL DEFAULT false,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted           BOOLEAN     NOT NULL DEFAULT false,
            CONSTRAINT uq_document_versions_doc_ver UNIQUE (learning_document_id, version_number)
        )
    """)

    # 3-8. document_chunks (chunk_tsv Generated Column 포함)
    op.execute("""
        CREATE TABLE document_chunks (
            id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            document_version_id  UUID          NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
            chunk_text           TEXT          NOT NULL,
            chunk_summary        TEXT,
            chunk_order          INTEGER       NOT NULL,
            token_count          INTEGER       NOT NULL DEFAULT 0,
            difficulty           VARCHAR(50),
            quality_score        NUMERIC(5,2),
            access_level         VARCHAR(50)   NOT NULL DEFAULT 'SHARED',
            is_active            BOOLEAN       NOT NULL DEFAULT true,
            created_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
            is_deleted           BOOLEAN       NOT NULL DEFAULT false,
            chunk_tsv            TSVECTOR GENERATED ALWAYS AS (
                to_tsvector('english', coalesce(chunk_text, ''))
            ) STORED,
            CONSTRAINT chk_document_chunks_quality_score
                CHECK (quality_score IS NULL OR quality_score BETWEEN 0 AND 100)
        )
    """)

    # 3-9. chunk_embeddings (pgvector)
    op.execute("""
        CREATE TABLE chunk_embeddings (
            id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            chunk_id       UUID         NOT NULL UNIQUE REFERENCES document_chunks(id) ON DELETE RESTRICT,
            embedding      vector(768)  NOT NULL,
            model_name     VARCHAR(100) NOT NULL,
            model_version  VARCHAR(50)  NOT NULL,
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            is_deleted     BOOLEAN      NOT NULL DEFAULT false
        )
    """)

    # 3-10. chunk_topics
    op.execute("""
        CREATE TABLE chunk_topics (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            chunk_id    UUID        NOT NULL REFERENCES document_chunks(id) ON DELETE RESTRICT,
            topic_id    UUID        NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted  BOOLEAN     NOT NULL DEFAULT false,
            CONSTRAINT uq_chunk_topics_chunk_topic UNIQUE (chunk_id, topic_id)
        )
    """)

    # 3-11. questions
    op.execute("""
        CREATE TABLE questions (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            certification_id UUID        NOT NULL REFERENCES certifications(id) ON DELETE RESTRICT,
            topic_id         UUID        NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
            source_chunk_id  UUID        REFERENCES document_chunks(id) ON DELETE RESTRICT,
            question_text    TEXT        NOT NULL,
            question_type    VARCHAR(50) NOT NULL,
            source_type      VARCHAR(50) NOT NULL,
            difficulty       VARCHAR(50) NOT NULL DEFAULT 'INTERMEDIATE',
            is_active        BOOLEAN     NOT NULL DEFAULT true,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted       BOOLEAN     NOT NULL DEFAULT false
        )
    """)

    # 3-12. choices
    op.execute("""
        CREATE TABLE choices (
            id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            question_id  UUID         NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
            choice_text  TEXT         NOT NULL,
            choice_label VARCHAR(10)  NOT NULL,
            is_correct   BOOLEAN      NOT NULL DEFAULT false,
            order_num    INTEGER      NOT NULL,
            created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
            is_deleted   BOOLEAN      NOT NULL DEFAULT false
        )
    """)

    # 3-13. answer_explanations
    op.execute("""
        CREATE TABLE answer_explanations (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            question_id      UUID        NOT NULL UNIQUE REFERENCES questions(id) ON DELETE RESTRICT,
            explanation_text TEXT        NOT NULL,
            source_chunk_id  UUID        REFERENCES document_chunks(id) ON DELETE RESTRICT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted       BOOLEAN     NOT NULL DEFAULT false
        )
    """)

    # 3-14. exam_sessions
    op.execute("""
        CREATE TABLE exam_sessions (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          UUID        NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            certification_id UUID        NOT NULL REFERENCES certifications(id) ON DELETE RESTRICT,
            exam_mode        VARCHAR(50) NOT NULL,
            total_questions  INTEGER     NOT NULL DEFAULT 0,
            correct_count    INTEGER     NOT NULL DEFAULT 0,
            time_limit_seconds INTEGER,
            elapsed_seconds  INTEGER,
            is_completed     BOOLEAN     NOT NULL DEFAULT false,
            started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at     TIMESTAMPTZ,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted       BOOLEAN     NOT NULL DEFAULT false,
            CONSTRAINT chk_exam_sessions_total_questions CHECK (total_questions >= 0),
            CONSTRAINT chk_exam_sessions_correct_count   CHECK (correct_count >= 0),
            CONSTRAINT chk_exam_sessions_correct_lte_total
                CHECK (correct_count <= total_questions)
        )
    """)

    # 3-15. user_attempts — [불변 이력] is_deleted=true 변경 및 DELETE 절대 금지
    op.execute("""
        CREATE TABLE user_attempts (
            id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id           UUID        NOT NULL REFERENCES exam_sessions(id) ON DELETE RESTRICT,
            question_id          UUID        NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
            selected_choice_ids  JSONB       NOT NULL DEFAULT '[]',
            is_correct           BOOLEAN     NOT NULL DEFAULT false,
            time_spent_seconds   INTEGER,
            answered_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted           BOOLEAN     NOT NULL DEFAULT false
        )
    """)

    # 3-16. pipeline_runs
    op.execute("""
        CREATE TABLE pipeline_runs (
            id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            learning_document_id UUID        NOT NULL REFERENCES learning_documents(id) ON DELETE RESTRICT,
            document_version_id  UUID        REFERENCES document_versions(id) ON DELETE RESTRICT,
            status               VARCHAR(50) NOT NULL DEFAULT 'PENDING',
            total_chunks         INTEGER,
            processed_chunks     INTEGER     NOT NULL DEFAULT 0,
            error_message        TEXT,
            started_at           TIMESTAMPTZ,
            completed_at         TIMESTAMPTZ,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted           BOOLEAN     NOT NULL DEFAULT false,
            CONSTRAINT chk_pipeline_runs_processed_chunks CHECK (processed_chunks >= 0)
        )
    """)

    # ──────────────────────────────────────────────
    # 4. B-tree 인덱스 (FK + 조회 최적화)
    # ──────────────────────────────────────────────
    op.execute("CREATE INDEX idx_exam_domains_certification_id ON exam_domains (certification_id)")
    op.execute("CREATE INDEX idx_topics_exam_domain_id ON topics (exam_domain_id)")
    op.execute("CREATE INDEX idx_learning_documents_certification_id ON learning_documents (certification_id)")
    op.execute("CREATE INDEX idx_document_versions_learning_document_id ON document_versions (learning_document_id)")
    op.execute("CREATE INDEX idx_document_chunks_document_version_id ON document_chunks (document_version_id)")
    op.execute("CREATE INDEX idx_chunk_topics_chunk_id ON chunk_topics (chunk_id)")
    op.execute("CREATE INDEX idx_chunk_topics_topic_id ON chunk_topics (topic_id)")
    op.execute("CREATE INDEX idx_questions_certification_id ON questions (certification_id)")
    op.execute("CREATE INDEX idx_questions_topic_id ON questions (topic_id)")
    op.execute(
        "CREATE INDEX idx_questions_source_chunk_id ON questions (source_chunk_id) "
        "WHERE source_chunk_id IS NOT NULL"
    )
    op.execute("CREATE INDEX idx_choices_question_id ON choices (question_id)")
    op.execute(
        "CREATE INDEX idx_answer_explanations_source_chunk_id ON answer_explanations (source_chunk_id) "
        "WHERE source_chunk_id IS NOT NULL"
    )
    op.execute("CREATE INDEX idx_exam_sessions_user_id ON exam_sessions (user_id)")
    op.execute("CREATE INDEX idx_exam_sessions_certification_id ON exam_sessions (certification_id)")
    op.execute("CREATE INDEX idx_user_attempts_session_id ON user_attempts (session_id)")
    op.execute("CREATE INDEX idx_user_attempts_question_id ON user_attempts (question_id)")
    op.execute("CREATE INDEX idx_pipeline_runs_learning_document_id ON pipeline_runs (learning_document_id)")
    op.execute(
        "CREATE INDEX idx_pipeline_runs_document_version_id ON pipeline_runs (document_version_id) "
        "WHERE document_version_id IS NOT NULL"
    )

    # 조회 최적화 복합 인덱스
    op.execute(
        "CREATE INDEX idx_questions_certification_id_is_active_difficulty "
        "ON questions (certification_id, is_active, difficulty) WHERE is_deleted = false"
    )
    op.execute(
        "CREATE INDEX idx_exam_sessions_user_id_created_at "
        "ON exam_sessions (user_id, created_at DESC) WHERE is_deleted = false"
    )
    op.execute(
        "CREATE INDEX idx_user_attempts_session_id_is_correct "
        "ON user_attempts (session_id, is_correct)"
    )
    op.execute(
        "CREATE INDEX idx_document_chunks_document_version_id_is_active "
        "ON document_chunks (document_version_id, is_active) WHERE is_deleted = false"
    )
    op.execute(
        "CREATE INDEX idx_pipeline_runs_learning_document_id_status "
        "ON pipeline_runs (learning_document_id, status)"
    )
    op.execute(
        "CREATE INDEX idx_code_values_code_group "
        "ON code_values (code_group) WHERE is_deleted = false AND is_active = true"
    )

    # ──────────────────────────────────────────────
    # 5. GIN 인덱스 (Full-text Search)
    # ──────────────────────────────────────────────
    op.execute(
        "CREATE INDEX idx_document_chunks_chunk_tsv ON document_chunks USING gin(chunk_tsv)"
    )

    # ──────────────────────────────────────────────
    # 6. updated_at 자동 갱신 트리거 (모든 테이블)
    # ──────────────────────────────────────────────
    for table in [
        "code_values", "certifications", "users", "exam_domains", "topics",
        "learning_documents", "document_versions", "document_chunks",
        "chunk_embeddings", "chunk_topics", "questions", "choices",
        "answer_explanations", "exam_sessions", "user_attempts", "pipeline_runs",
    ]:
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)


def downgrade() -> None:
    # 트리거 제거
    for table in [
        "pipeline_runs", "user_attempts", "exam_sessions", "answer_explanations",
        "choices", "questions", "chunk_topics", "chunk_embeddings",
        "document_chunks", "document_versions", "learning_documents",
        "topics", "exam_domains", "users", "certifications", "code_values",
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")

    # 테이블 제거 (의존성 역순)
    for table in [
        "pipeline_runs", "user_attempts", "exam_sessions", "answer_explanations",
        "choices", "questions", "chunk_topics", "chunk_embeddings",
        "document_chunks", "document_versions", "learning_documents",
        "topics", "exam_domains", "users", "certifications", "code_values",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    op.execute('DROP EXTENSION IF EXISTS "vector"')
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
