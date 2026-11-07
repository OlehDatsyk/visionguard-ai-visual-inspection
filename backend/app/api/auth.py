"""Registration, login, profile, workspaces and user settings."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, owned_workspace, rate_limit_auth
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, rate_limiter, verify_password
from app.core.storage import get_storage
from app.database.session import get_db
from app.models import AppSetting, User, Workspace
from app.schemas.common import (
    AccountDelete,
    LoginIn,
    Message,
    PasswordChange,
    RegisterIn,
    SettingsIn,
    TokenOut,
    UserOut,
    UserUpdate,
    WorkspaceIn,
    WorkspaceOut,
)
from app.vision.profiles import CATEGORIES

router = APIRouter()


def _token(user: User) -> TokenOut:
    token, ttl = create_access_token(user.id, user.token_version)
    return TokenOut(access_token=token, expires_in=ttl, user=UserOut.model_validate(user))


@router.post("/auth/register", response_model=TokenOut, status_code=201, tags=["Authentication"],
             dependencies=[Depends(rate_limit_auth)])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    user = User(email=body.email.lower(), full_name=body.full_name.strip(), password_hash=hash_password(body.password))
    user.workspaces.append(Workspace(name="My workspace"))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this e-mail already exists.") from exc
    return _token(user)


@router.post("/auth/login", response_model=TokenOut, tags=["Authentication"], dependencies=[Depends(rate_limit_auth)])
def login(body: LoginIn, db: Session = Depends(get_db)):
    rate_limiter.check(f"login:{body.email.lower()}", get_settings().auth_rate_limit_per_minute)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    valid = verify_password(body.password, user.password_hash if user else None)
    if not valid or user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect e-mail or password.")
    return _token(user)


@router.post("/auth/logout", response_model=Message, tags=["Authentication"])
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Tokens carry the version they were issued with, so this ends every session for the account.
    user.token_version += 1
    db.commit()
    return Message(message="Signed out")


@router.get("/users/me", response_model=UserOut, tags=["Users"])
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/users/me", response_model=UserOut, tags=["Users"])
def update_me(body: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.full_name = body.full_name.strip()
    db.commit()
    return user


@router.post("/users/me/password", response_model=TokenOut, tags=["Users"], dependencies=[Depends(rate_limit_auth)])
def change_password(body: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The current password is incorrect.")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    db.commit()
    return _token(user)


@router.post("/users/me/delete", response_model=Message, tags=["Users"], dependencies=[Depends(rate_limit_auth)])
def delete_account(body: AccountDelete, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The password is incorrect.")
    get_storage().delete_prefix(user.id)
    db.delete(user)
    db.commit()
    return Message(message="Account and stored files deleted")


# Workspaces ---------------------------------------------------------------------------------------
@router.get("/workspaces", response_model=list[WorkspaceOut], tags=["Workspaces"])
def list_workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Workspace).where(Workspace.owner_id == user.id).order_by(Workspace.is_demo, Workspace.created_at)))


@router.post("/workspaces", response_model=WorkspaceOut, status_code=201, tags=["Workspaces"])
def create_workspace(body: WorkspaceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workspace = Workspace(owner_id=user.id, name=body.name.strip())
    db.add(workspace)
    db.commit()
    return workspace


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut, tags=["Workspaces"])
def rename_workspace(workspace_id: str, body: WorkspaceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workspace = owned_workspace(db, user, workspace_id)
    workspace.name = body.name.strip()
    db.commit()
    return workspace


@router.delete("/workspaces/{workspace_id}", status_code=204, tags=["Workspaces"])
def delete_workspace(workspace_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workspace = owned_workspace(db, user, workspace_id)
    real_count = sum(1 for w in user.workspaces if not w.is_demo)
    if not workspace.is_demo and real_count <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "You must keep at least one workspace.")
    get_storage().delete_prefix(f"{user.id}/{workspace.id}")
    db.delete(workspace)
    db.commit()


# Settings -----------------------------------------------------------------------------------------
@router.get("/settings", response_model=SettingsIn, tags=["Settings"])
def read_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    setting = db.scalar(select(AppSetting).where(AppSetting.user_id == user.id))
    return SettingsIn(**(setting.preferences if setting else {}))


@router.put("/settings", response_model=SettingsIn, tags=["Settings"])
def write_settings(body: SettingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.default_category is not None and body.default_category not in CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown inspection category.")
    setting = db.scalar(select(AppSetting).where(AppSetting.user_id == user.id))
    if setting is None:
        setting = AppSetting(user_id=user.id)
        db.add(setting)
    setting.preferences = body.model_dump()
    db.commit()
    return body
