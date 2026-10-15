"""Settings endpoints: organization profile, PDF export design, appearance.

- GET /settings/org -> any authenticated user (the UI shows the org name).
- PUT /settings/org -> settings.org.manage OR system.settings.manage.
- PUT /settings/pdf-design -> same gate; audited on every change.
- POST /settings/pdf-preview -> renders a sample PDF with a draft design so
  administrators can verify the document look before saving.
- GET/PUT /me/preferences -> any authenticated user (theme mode, accent, font).
"""

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.context import current_request_id
from app.schemas.settings import (
    OrgSettingsOut,
    OrgSettingsUpdate,
    PdfDesignOut,
    PdfDesignPreviewRequest,
    PdfDesignUpdate,
    UserPreferencesOut,
    UserPreferencesUpdate,
)
from app.services import pdf_service, settings_service

router = APIRouter(tags=["Settings"])

SETTINGS_MANAGE_PERMISSIONS = ("settings.org.manage", "system.settings.manage")


def _auth(request: Request, user: CurrentUser) -> None:
    request.state.user = user


@router.get("/settings/org", response_model=OrgSettingsOut)
def get_org_settings(request: Request, db: DbSession, user: CurrentUser):
    _auth(request, user)
    return OrgSettingsOut(**settings_service.get_org_settings(db))


@router.put("/settings/org", response_model=OrgSettingsOut,
            dependencies=[Depends(require_permission(*SETTINGS_MANAGE_PERMISSIONS))])
def update_org_settings(request: Request, db: DbSession, user: CurrentUser, body: OrgSettingsUpdate):
    _auth(request, user)
    updated = settings_service.update_org_settings(
        db, body.model_dump(exclude_unset=True), user, current_request_id()
    )
    db.commit()
    return OrgSettingsOut(**updated)


@router.get("/settings/pdf-design", response_model=PdfDesignOut,
            dependencies=[Depends(require_permission(*SETTINGS_MANAGE_PERMISSIONS))])
def get_pdf_design(request: Request, db: DbSession, user: CurrentUser):
    _auth(request, user)
    return PdfDesignOut(**settings_service.get_pdf_design(db))


@router.put("/settings/pdf-design", response_model=PdfDesignOut,
            dependencies=[Depends(require_permission(*SETTINGS_MANAGE_PERMISSIONS))])
def update_pdf_design(request: Request, db: DbSession, user: CurrentUser, body: PdfDesignUpdate):
    _auth(request, user)
    updated = settings_service.update_pdf_design(
        db, body.model_dump(exclude_unset=True), user, current_request_id()
    )
    db.commit()
    return PdfDesignOut(**updated)


@router.post("/settings/pdf-preview",
             dependencies=[Depends(require_permission(*SETTINGS_MANAGE_PERMISSIONS))])
def preview_pdf_design(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    body: PdfDesignPreviewRequest,
):
    _auth(request, user)
    draft = settings_service.preview_pdf_design(
        db, body.design.model_dump(exclude_unset=True)
    )
    org = settings_service.get_org_settings(db)
    sample_rows = [
        ["TSK-2026-0007", "Vendor invoice reconciliation", "in_progress", "high", "Amara Okafor", "2026-11-02", "65"],
        ["TSK-2026-0011", "Quarterly compliance audit", "under_review", "critical", "Daniel Reyes", "2026-10-28", "90"],
        ["TSK-2026-0014", "Warehouse stock migration", "open", "medium", "Priya Nair", "2026-12-15", "10"],
        ["TSK-2026-0019", "Fleet maintenance scheduling", "completed", "low", "Jonas Weber", "2026-09-30", "100"],
    ]
    sections = [{
        "heading": "Document preview",
        "paragraph": "This sample uses placeholder data. Saved changes apply to every PDF export.",
        "table": {
            "columns": ["Task", "Title", "Status", "Priority", "Accountable PM", "Due", "%"],
            "rows": sample_rows,
        },
    }]
    content = pdf_service.render_pdf(
        draft, org,
        title="PDF Design Preview",
        subtitle="Sample export document",
        sections=sections,
        generated_by=user.full_name,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="pdf_design_preview.pdf"'},
    )


@router.get("/me/preferences", response_model=UserPreferencesOut)
def get_my_preferences(request: Request, db: DbSession, user: CurrentUser):
    _auth(request, user)
    return UserPreferencesOut(**settings_service.get_user_preferences(user))


@router.put("/me/preferences", response_model=UserPreferencesOut)
def update_my_preferences(request: Request, db: DbSession, user: CurrentUser, body: UserPreferencesUpdate):
    _auth(request, user)
    updated = settings_service.update_user_preferences(
        db, user, body.model_dump(exclude_unset=True)
    )
    db.commit()
    return UserPreferencesOut(**updated)
