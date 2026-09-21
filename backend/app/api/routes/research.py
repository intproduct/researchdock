import hashlib
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep, TokenDep
from app.models import User, get_datetime_utc
from app.research_models import (
    CopyCreate,
    CopyRepositoryBinding,
    Device,
    DeviceCreate,
    DevicePublic,
    Observation,
    Project,
    ProjectCreate,
    ProjectHistoryPage,
    ProjectRevision,
    ProjectRevisionPublic,
    ProjectSnapshot,
    ProjectUpdate,
    Repository,
    RepositoryCreate,
    RepositoryPublic,
    RepositoryUpdate,
    WorkingCopy,
)

router = APIRouter(tags=["research"])


def require_project(session, project_id: uuid.UUID, owner_id: uuid.UUID) -> Project:
    project = session.get(Project, project_id)
    if not project or project.owner_id != owner_id:
        raise HTTPException(404, "项目不存在")
    return project


def record_revision(
    session,
    *,
    project_id: uuid.UUID,
    revision: int,
    content: ProjectSnapshot,
    actor_id: uuid.UUID | None,
    origin: str,
    project_updated_at,
) -> None:
    """Stage a snapshot in the caller's transaction; never commits on its own."""
    session.add(
        ProjectRevision(
            project_id=project_id,
            revision=revision,
            snapshot=content.model_dump(),
            actor_id=actor_id,
            origin=origin,
            project_updated_at=project_updated_at,
        )
    )


def get_device(session: SessionDep, token: TokenDep) -> Device:
    digest = hashlib.sha256(token.encode()).hexdigest()
    device = session.exec(select(Device).where(Device.token_hash == digest)).first()
    if not device or device.revoked:
        raise HTTPException(401, "设备凭据无效或已撤销")
    owner = session.get(User, device.owner_id)
    if not owner or not owner.is_active:
        raise HTTPException(401, "设备所属账户不可用")
    return device


AgentDevice = Annotated[Device, Depends(get_device)]


@router.get("/projects", response_model=list[Project])
def projects(session: SessionDep, user: CurrentUser):
    return session.exec(
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
    ).all()


@router.get("/copies", response_model=list[WorkingCopy])
def all_copies(session: SessionDep, user: CurrentUser):
    return session.exec(
        select(WorkingCopy).join(Project).where(Project.owner_id == user.id)
    ).all()


@router.post("/projects", response_model=Project, status_code=201)
def create_project(body: ProjectCreate, session: SessionDep, user: CurrentUser):
    project = Project(**body.model_dump(), owner_id=user.id)
    session.add(project)
    session.flush()
    record_revision(
        session,
        project_id=project.id,
        revision=project.revision,
        content=ProjectSnapshot(
            name=project.name,
            description=project.description,
            stage=project.stage,
            status_note=project.status_note,
            next_step=project.next_step,
        ),
        actor_id=user.id,
        origin="created",
        project_updated_at=project.updated_at,
    )
    session.commit()
    session.refresh(project)
    return project


@router.put("/projects/{project_id}", response_model=Project)
def edit_project(
    project_id: uuid.UUID, body: ProjectUpdate, session: SessionDep, user: CurrentUser
):
    require_project(session, project_id, user.id)
    updated_at = get_datetime_utc()
    result = session.execute(
        update(Project)
        .where(
            Project.id == project_id,
            Project.owner_id == user.id,
            Project.revision == body.revision,
        )
        .values(
            **body.model_dump(exclude={"revision"}),
            revision=body.revision + 1,
            updated_at=updated_at,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(409, "项目已被更新，请刷新后再保存")
    # Snapshot comes from the validated request body, not the identity map, so
    # a stale in-session Project object can never be mistaken for new data.
    record_revision(
        session,
        project_id=project_id,
        revision=body.revision + 1,
        content=ProjectSnapshot(
            name=body.name,
            description=body.description,
            stage=body.stage,
            status_note=body.status_note,
            next_step=body.next_step,
        ),
        actor_id=user.id,
        origin="updated",
        project_updated_at=updated_at,
    )
    session.commit()
    return session.get(Project, project_id)


@router.get("/projects/{project_id}/history", response_model=ProjectHistoryPage)
def project_history(
    project_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before_revision: Annotated[int | None, Query(ge=1)] = None,
):
    require_project(session, project_id, user.id)
    statement = (
        select(ProjectRevision)
        .where(ProjectRevision.project_id == project_id)
        .order_by(ProjectRevision.revision.desc())
        .limit(limit + 1)
    )
    if before_revision is not None:
        statement = statement.where(ProjectRevision.revision < before_revision)
    rows = session.exec(statement).all()
    items = [ProjectRevisionPublic.model_validate(row) for row in rows[:limit]]
    next_before = items[-1].revision if len(rows) > limit else None
    return ProjectHistoryPage(items=items, next_before_revision=next_before)


@router.get("/projects/{project_id}/copies", response_model=list[WorkingCopy])
def project_copies(project_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    require_project(session, project_id, user.id)
    return session.exec(
        select(WorkingCopy)
        .where(WorkingCopy.project_id == project_id)
        .order_by(WorkingCopy.local_path)
    ).all()


def require_repository(
    session, repository_id: uuid.UUID, owner_id: uuid.UUID
) -> Repository:
    repository = session.get(Repository, repository_id)
    if not repository:
        raise HTTPException(404, "仓库不存在")
    # Ownership is derived from the parent project; never trust the id alone.
    require_project(session, repository.project_id, owner_id)
    return repository


@router.get(
    "/projects/{project_id}/repositories", response_model=list[RepositoryPublic]
)
def list_repositories(project_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    require_project(session, project_id, user.id)
    rows = session.exec(
        select(Repository)
        .where(Repository.project_id == project_id)
        .order_by(Repository.created_at, Repository.id)
    ).all()
    return [RepositoryPublic.model_validate(r) for r in rows]


@router.post(
    "/projects/{project_id}/repositories",
    response_model=RepositoryPublic,
    status_code=201,
)
def create_repository(
    project_id: uuid.UUID, body: RepositoryCreate, session: SessionDep, user: CurrentUser
):
    require_project(session, project_id, user.id)
    repository = Repository(project_id=project_id, name=body.name)
    session.add(repository)
    session.commit()
    session.refresh(repository)
    return RepositoryPublic.model_validate(repository)


@router.put("/repositories/{repository_id}", response_model=RepositoryPublic)
def rename_repository(
    repository_id: uuid.UUID,
    body: RepositoryUpdate,
    session: SessionDep,
    user: CurrentUser,
):
    require_repository(session, repository_id, user.id)
    updated_at = get_datetime_utc()
    # Atomic conditional rename: the expected revision guards against two
    # sessions editing the same repository; a stale expectation writes nothing.
    result = session.execute(
        update(Repository)
        .where(Repository.id == repository_id, Repository.revision == body.revision)
        .values(name=body.name, revision=body.revision + 1, updated_at=updated_at)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(409, "仓库已被更新，请刷新后再保存")
    session.commit()
    return RepositoryPublic.model_validate(session.get(Repository, repository_id))


@router.put("/copies/{copy_id}/repository", response_model=WorkingCopy)
def bind_copy_repository(
    copy_id: uuid.UUID,
    body: CopyRepositoryBinding,
    session: SessionDep,
    user: CurrentUser,
):
    copy = session.get(WorkingCopy, copy_id)
    if not copy:
        raise HTTPException(404, "副本不存在")
    # Only the owner of the copy's project may change the binding.
    require_project(session, copy.project_id, user.id)
    if body.repository_id is not None:
        # Validate ownership before the same-project check so a nonexistent id
        # and another account's repository are indistinguishable (both 404);
        # only a repository in the caller's own *other* project yields 422.
        require_repository(session, body.repository_id, user.id)
        target = session.get(Repository, body.repository_id)
        if target.project_id != copy.project_id:
            raise HTTPException(422, "仓库不属于该副本所在项目")
    if copy.binding_revision != body.binding_revision:
        # A stale expectation is a conflict even when the target matches, so an
        # idempotent-looking retry can never mask a real concurrent change.
        raise HTTPException(409, "关联已被更新，请刷新后再提交")
    if copy.repository_id == body.repository_id:
        # Same target, valid expectation: no-op, return as-is without bumping.
        return copy
    result = session.execute(
        update(WorkingCopy)
        .where(
            WorkingCopy.id == copy_id,
            WorkingCopy.binding_revision == body.binding_revision,
        )
        .values(
            repository_id=body.repository_id,
            binding_revision=body.binding_revision + 1,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(409, "关联已被更新，请刷新后再提交")
    session.commit()
    session.refresh(copy)
    return copy


@router.get("/devices", response_model=list[DevicePublic])
def devices(session: SessionDep, user: CurrentUser):
    return session.exec(
        select(Device)
        .where(Device.owner_id == user.id)
        .order_by(Device.created_at.desc())
    ).all()


@router.post("/devices", status_code=201)
def enroll_device(body: DeviceCreate, session: SessionDep, user: CurrentUser):
    token = "rm_device_" + secrets.token_urlsafe(40)
    device = Device(
        **body.model_dump(),
        owner_id=user.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return {"device": DevicePublic.model_validate(device), "token": token}


@router.post("/devices/{device_id}/revoke", response_model=DevicePublic)
def revoke_device(device_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    device = session.get(Device, device_id)
    if not device or device.owner_id != user.id:
        raise HTTPException(404, "设备不存在")
    device.revoked = True
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@router.get("/agent/projects", response_model=list[Project])
def agent_projects(session: SessionDep, device: AgentDevice):
    return session.exec(
        select(Project).where(Project.owner_id == device.owner_id)
    ).all()


@router.post("/agent/heartbeat")
def heartbeat(session: SessionDep, device: AgentDevice):
    device.last_seen = get_datetime_utc()
    session.add(device)
    session.commit()
    return {"ok": True}


@router.get(
    "/agent/projects/{project_id}/repositories",
    response_model=list[RepositoryPublic],
)
def agent_repositories(
    project_id: uuid.UUID, session: SessionDep, device: AgentDevice
):
    # Read-only listing scoped to the device owner's projects; a revoked device
    # is already rejected by get_device with 401.
    require_project(session, project_id, device.owner_id)
    rows = session.exec(
        select(Repository)
        .where(Repository.project_id == project_id)
        .order_by(Repository.created_at, Repository.id)
    ).all()
    return [RepositoryPublic.model_validate(r) for r in rows]


@router.post("/agent/copies", response_model=WorkingCopy)
def bind_copy(body: CopyCreate, session: SessionDep, device: AgentDevice):
    require_project(session, body.project_id, device.owner_id)
    if body.repository_id is not None:
        # Ownership first: a nonexistent id and another account's repository are
        # both 404 (no existence leak); only the owner's own other project is 422.
        require_repository(session, body.repository_id, device.owner_id)
        target = session.get(Repository, body.repository_id)
        if target.project_id != body.project_id:
            raise HTTPException(422, "仓库不属于该项目")
    existing = session.exec(
        select(WorkingCopy).where(
            WorkingCopy.device_id == device.id,
            WorkingCopy.local_path == body.local_path,
        )
    ).first()
    if existing:
        if existing.project_id != body.project_id:
            raise HTTPException(409, "该目录已绑定其他项目")
        if body.repository_id is None:
            # Legacy/unspecified registration: keep the current binding as-is,
            # never unbind or auto-create a repository. Old agents stay usable.
            return existing
        if existing.repository_id == body.repository_id:
            # Idempotent retry of a lost response: return the existing binding
            # unchanged (same id/sequence/binding_revision).
            return existing
        # The device may not reclassify an already-bound copy; the owner must
        # correct the association via the web interface.
        raise HTTPException(409, "该目录的仓库关联与请求不一致，请在网页端更正")
    copy = WorkingCopy(
        project_id=body.project_id,
        local_path=body.local_path,
        repository_id=body.repository_id,
        # A copy registered with an explicit repository starts at binding 1;
        # an uncategorized one stays at the 0 default.
        binding_revision=1 if body.repository_id is not None else 0,
        device_id=device.id,
    )
    session.add(copy)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # A concurrent first registration of the same (device, path) won the
        # unique constraint between our existence check and commit. Re-read the
        # winner so identical concurrent parameters converge on the same id
        # instead of erroring; a winner with different parameters still 409s.
        winner = session.exec(
            select(WorkingCopy).where(
                WorkingCopy.device_id == device.id,
                WorkingCopy.local_path == body.local_path,
            )
        ).first()
        if not winner:
            raise HTTPException(409, "目录已登记，请重试以读取已有绑定")
        if winner.project_id != body.project_id:
            raise HTTPException(409, "该目录已绑定其他项目")
        if body.repository_id is not None and winner.repository_id != body.repository_id:
            raise HTTPException(409, "该目录的仓库关联与请求不一致，请在网页端更正")
        return winner
    session.refresh(copy)
    return copy


@router.post("/agent/copies/{copy_id}/observations")
def observe(
    copy_id: uuid.UUID, body: Observation, session: SessionDep, device: AgentDevice
):
    copy = session.get(WorkingCopy, copy_id)
    if not copy or copy.device_id != device.id:
        raise HTTPException(404, "副本不存在")
    values = body.model_dump()
    # The agent reports metadata, never URLs with embedded passwords or query tokens.
    remote = values.get("remote_url")
    if remote and (
        "?" in remote
        or "#" in remote
        or ("://" in remote and "@" in remote.split("://", 1)[1].split("/", 1)[0])
    ):
        raise HTTPException(422, "remote_url 不能包含凭据或查询参数")
    values["received_at"] = get_datetime_utc()
    result = session.execute(
        update(WorkingCopy)
        .where(
            WorkingCopy.id == copy_id,
            WorkingCopy.device_id == device.id,
            WorkingCopy.sequence < body.sequence,
        )
        .values(**values)
    )
    device.last_seen = get_datetime_utc()
    session.add(device)
    session.commit()
    return {"ok": True, "accepted": result.rowcount == 1}
