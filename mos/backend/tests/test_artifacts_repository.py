from app.db.enums import ArtifactTypeEnum, UserRoleEnum
from app.db.models import Client, User
from app.db.repositories.artifacts import ArtifactsRepository


def _create_client(db_session):
    client = Client(org_id="00000000-0000-0000-0000-000000000001", name="Artifacts Client", industry="SaaS")
    db_session.add(client)
    db_session.commit()
    db_session.refresh(client)
    return client


def test_insert_artifact_with_unresolvable_created_by_user_does_not_fail(db_session):
    client = _create_client(db_session)
    repo = ArtifactsRepository(db_session)

    artifact = repo.insert(
        org_id=str(client.org_id),
        client_id=str(client.id),
        artifact_type=ArtifactTypeEnum.client_canon,
        data={"hello": "world"},
        created_by_user="user_36iTMtClnkSdcRBDFuqvcD72Dwt",
    )

    assert artifact is not None
    assert artifact.created_by_user is None


def test_insert_artifact_resolves_created_by_user_from_clerk_user_id(db_session):
    client = _create_client(db_session)
    user = User(
        org_id=str(client.org_id),
        clerk_user_id="user_36iTMtClnkSdcRBDFuqvcD72Dwt",
        email="artifact-user@example.com",
        role=UserRoleEnum.admin,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    repo = ArtifactsRepository(db_session)
    artifact = repo.insert(
        org_id=str(client.org_id),
        client_id=str(client.id),
        artifact_type=ArtifactTypeEnum.client_canon,
        data={"hello": "world"},
        created_by_user="user_36iTMtClnkSdcRBDFuqvcD72Dwt",
    )

    assert str(artifact.created_by_user) == str(user.id)
