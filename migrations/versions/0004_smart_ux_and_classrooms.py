"""smart_ux_and_classrooms

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01 19:55:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


#  Alembic identifikatorlari
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    # 1. classrooms jadvali
    if 'classrooms' not in existing_tables:
        op.create_table(
            'classrooms',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('teacher_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
            sa.Column('name', sa.String(length=120), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('code', sa.String(length=16), nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], name=op.f('fk_classrooms_teacher_id_users'), ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_classrooms')),
            comment='Sinf va o\'quv guruhlari'
        )
        with op.batch_alter_table('classrooms', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_classrooms_code'), ['code'], unique=True)
            batch_op.create_index(batch_op.f('ix_classrooms_created_at'), ['created_at'], unique=False)
            batch_op.create_index(batch_op.f('ix_classrooms_name'), ['name'], unique=False)
            batch_op.create_index(batch_op.f('ix_classrooms_teacher_id'), ['teacher_id'], unique=False)
            batch_op.create_index('ix_classrooms_teacher_active', ['teacher_id', 'is_active'], unique=False)

    # 2. classroom_members jadvali
    if 'classroom_members' not in existing_tables:
        op.create_table(
            'classroom_members',
            sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
            sa.Column('classroom_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
            sa.Column('joined_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['classroom_id'], ['classrooms.id'], name=op.f('fk_classroom_members_classroom_id_classrooms'), ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_classroom_members_user_id_users'), ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_classroom_members')),
            sa.UniqueConstraint('classroom_id', 'user_id', name='uq_classroom_member'),
            comment='Guruh / Sinf a\'zolari'
        )
        with op.batch_alter_table('classroom_members', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_classroom_members_classroom_id'), ['classroom_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_classroom_members_user_id'), ['user_id'], unique=False)
            batch_op.create_index('ix_classroom_members_class_user', ['classroom_id', 'user_id'], unique=False)

    # 3. parent_student_links jadvali
    if 'parent_student_links' not in existing_tables:
        op.create_table(
            'parent_student_links',
            sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
            sa.Column('student_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
            sa.Column('parent_telegram_id', sa.BigInteger(), nullable=False),
            sa.Column('parent_name', sa.String(length=128), nullable=True),
            sa.Column('relationship_type', sa.String(length=32), server_default='parent', nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['student_id'], ['users.id'], name=op.f('fk_parent_student_links_student_id_users'), ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_parent_student_links')),
            comment='Ota-ona va o\'quvchi bog\'lanishi'
        )
        with op.batch_alter_table('parent_student_links', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_parent_student_links_parent_telegram_id'), ['parent_telegram_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_parent_student_links_student_id'), ['student_id'], unique=False)
            batch_op.create_index('ix_parent_links_student_parent', ['student_id', 'parent_telegram_id'], unique=False)

    # 4. student_mistakes jadvali
    if 'student_mistakes' not in existing_tables:
        op.create_table(
            'student_mistakes',
            sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
            sa.Column('test_id', sa.Integer(), nullable=False),
            sa.Column('attempt_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
            sa.Column('question_number', sa.Integer(), nullable=False),
            sa.Column('given_answer', sa.String(length=8), nullable=False),
            sa.Column('correct_answer', sa.String(length=8), nullable=False),
            sa.Column('is_resolved', sa.Boolean(), server_default='0', nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('resolved_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['attempt_id'], ['attempts.id'], name=op.f('fk_student_mistakes_attempt_id_attempts'), ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['test_id'], ['tests.id'], name=op.f('fk_student_mistakes_test_id_tests'), ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_student_mistakes_user_id_users'), ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_student_mistakes')),
            comment='O\'quvchi xatolari daftari'
        )
        with op.batch_alter_table('student_mistakes', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_student_mistakes_attempt_id'), ['attempt_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_student_mistakes_is_resolved'), ['is_resolved'], unique=False)
            batch_op.create_index(batch_op.f('ix_student_mistakes_test_id'), ['test_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_student_mistakes_user_id'), ['user_id'], unique=False)
            batch_op.create_index('ix_student_mistakes_test_qnum', ['test_id', 'question_number'], unique=False)
            batch_op.create_index('ix_student_mistakes_user_resolved', ['user_id', 'is_resolved'], unique=False)

    # 5. question_explanations jadvali
    if 'question_explanations' not in existing_tables:
        op.create_table(
            'question_explanations',
            sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
            sa.Column('test_id', sa.Integer(), nullable=False),
            sa.Column('question_number', sa.Integer(), nullable=False),
            sa.Column('explanation_text', sa.Text(), nullable=False),
            sa.Column('media_file_id', sa.String(length=256), nullable=True),
            sa.Column('media_type', sa.String(length=16), server_default='text', nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['test_id'], ['tests.id'], name=op.f('fk_question_explanations_test_id_tests'), ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_question_explanations')),
            comment='Savollar yechimlari va tushuntirishlari'
        )
        with op.batch_alter_table('question_explanations', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_question_explanations_test_id'), ['test_id'], unique=False)
            batch_op.create_index('ix_question_explanations_test_qnum', ['test_id', 'question_number'], unique=False)

    # 6. question_appeals jadvali
    if 'question_appeals' not in existing_tables:
        op.create_table(
            'question_appeals',
            sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
            sa.Column('test_id', sa.Integer(), nullable=False),
            sa.Column('question_number', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
            sa.Column('appeal_text', sa.Text(), nullable=False),
            sa.Column('reply_text', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('replied_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['test_id'], ['tests.id'], name=op.f('fk_question_appeals_test_id_tests'), ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_question_appeals_user_id_users'), ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_question_appeals')),
            comment='Savollar yuzasidan e\'tiroz va apellyatsiyalar'
        )
        with op.batch_alter_table('question_appeals', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_question_appeals_test_id'), ['test_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_question_appeals_user_id'), ['user_id'], unique=False)
            batch_op.create_index('ix_question_appeals_test_qnum', ['test_id', 'question_number'], unique=False)
            batch_op.create_index('ix_question_appeals_user', ['user_id'], unique=False)

    # 7. tests jadvalidagi yangi ustunlar
    test_cols = {c['name'] for c in insp.get_columns('tests')}
    with op.batch_alter_table('tests', schema=None) as batch_op:
        if 'channel_id' not in test_cols:
            batch_op.add_column(sa.Column('channel_id', sa.BigInteger(), nullable=True))
        if 'channel_message_id' not in test_cols:
            batch_op.add_column(sa.Column('channel_message_id', sa.Integer(), nullable=True))
        if 'results_posted_at' not in test_cols:
            batch_op.add_column(sa.Column('results_posted_at', sa.DateTime(), nullable=True))
        if 'is_randomized' not in test_cols:
            batch_op.add_column(sa.Column('is_randomized', sa.Boolean(), server_default='0', nullable=False))
        if 'random_questions_count' not in test_cols:
            batch_op.add_column(sa.Column('random_questions_count', sa.Integer(), nullable=True))
        if 'classroom_id' not in test_cols:
            batch_op.add_column(sa.Column('classroom_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(batch_op.f('fk_tests_classroom_id_classrooms'), 'classrooms', ['classroom_id'], ['id'], ondelete='SET NULL')
            batch_op.create_index(batch_op.f('ix_tests_classroom_id'), ['classroom_id'], unique=False)
        if 'allow_practice' not in test_cols:
            batch_op.add_column(sa.Column('allow_practice', sa.Boolean(), server_default='1', nullable=False))

    # 8. attempts jadvalidagi yangi ustunlar
    attempt_cols = {c['name'] for c in insp.get_columns('attempts')}
    with op.batch_alter_table('attempts', schema=None) as batch_op:
        if 'question_order' not in attempt_cols:
            batch_op.add_column(sa.Column('question_order', sa.String(length=512), nullable=True))
        if 'effective_key' not in attempt_cols:
            batch_op.add_column(sa.Column('effective_key', sa.String(length=256), nullable=True))
        if 'is_practice' not in attempt_cols:
            batch_op.add_column(sa.Column('is_practice', sa.Boolean(), server_default='0', nullable=False))
            batch_op.create_index(batch_op.f('ix_attempts_is_practice'), ['is_practice'], unique=False)
        if 'attempt_number' not in attempt_cols:
            batch_op.add_column(sa.Column('attempt_number', sa.Integer(), server_default='1', nullable=False))

    # 9. users jadvalidagi yangi ustunlar
    user_cols = {c['name'] for c in insp.get_columns('users')}
    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'phone' not in user_cols:
            batch_op.add_column(sa.Column('phone', sa.String(length=24), nullable=True))
            batch_op.create_index(batch_op.f('ix_users_phone'), ['phone'], unique=False)
        if 'is_registered' not in user_cols:
            batch_op.add_column(sa.Column('is_registered', sa.Boolean(), server_default='0', nullable=False))
            batch_op.create_index(batch_op.f('ix_users_is_registered'), ['is_registered'], unique=False)
        if 'xp' not in user_cols:
            batch_op.add_column(sa.Column('xp', sa.Integer(), server_default='0', nullable=False))
            batch_op.create_index('ix_users_xp_desc', ['xp'], unique=False)
        if 'streak_days' not in user_cols:
            batch_op.add_column(sa.Column('streak_days', sa.Integer(), server_default='0', nullable=False))
        if 'streak_updated_on' not in user_cols:
            batch_op.add_column(sa.Column('streak_updated_on', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_table('question_appeals')
    op.drop_table('question_explanations')
    op.drop_table('student_mistakes')
    op.drop_table('parent_student_links')
    op.drop_table('classroom_members')
    op.drop_table('classrooms')
