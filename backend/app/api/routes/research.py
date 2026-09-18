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


@router.post("/agent/copies", response_model=WorkingCopy)
def bind_copy(body: CopyCreate, session: SessionDep, device: AgentDevice):
    require_project(session, body.project_id, device.owner_id)
    existing = session.exec(
        select(WorkingCopy).where(
            WorkingCopy.device_id == device.id,
            WorkingCopy.local_path == body.local_path,
        )
    ).first()
    if existing:
        if existing.project_id != body.project_id:
            raise HTTPException(409, "该目录已绑定其他项目")
        return existing
    copy = WorkingCopy(**body.model_dump(), device_id=device.id)
    session.add(copy)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "目录已登记，请重试以读取已有绑定")
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
