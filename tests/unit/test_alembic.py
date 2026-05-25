from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_single_expected_head() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["20260525_0005"]


def test_initial_schema_migration_chain_is_linear() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    revisions = list(script.walk_revisions())

    assert [revision.revision for revision in revisions] == [
        "20260525_0005",
        "20260524_0004",
        "20260524_0003",
        "20260523_0002",
        "20260523_0001",
    ]
    assert revisions[0].down_revision == "20260524_0004"
    assert revisions[1].down_revision == "20260524_0003"
    assert revisions[2].down_revision == "20260523_0002"
    assert revisions[3].down_revision == "20260523_0001"
    assert revisions[4].down_revision is None
