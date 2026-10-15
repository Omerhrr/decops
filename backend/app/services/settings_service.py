"""Application settings service: organization profile, PDF export design,
and per-user appearance preferences.

Org-level values live in the app_settings keyed JSON store merged over
defaults, so partial updates and new keys are safe. Appearance preferences
are stored per user and validated against the same option sets the UI offers.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailedError
from app.models import AppSetting, User
from app.services import audit_service

THEME_MODES = ("light", "dark", "system")
ACCENT_COLORS = ("emerald", "blue", "violet", "rose", "amber", "slate")
FONT_CHOICES = ("inter", "system", "serif", "mono")

PAPER_SIZES = ("A4", "Letter")
ORIENTATIONS = ("portrait", "landscape")
PDF_FONTS = ("sans", "serif", "mono")
TABLE_STYLES = ("striped", "plain", "bordered")

ORG_DEFAULTS = {
    "org_name": "Interdec",
    "org_tagline": "Operations Management",
}

PDF_DESIGN_DEFAULTS = {
    "paper_size": "A4",
    "orientation": "portrait",
    "accent_color": "#0f766e",
    "font_family": "sans",
    "font_size_pt": 9,
    "show_cover_page": True,
    "header_show_logo": True,
    "header_show_org_name": True,
    "footer_text": "Confidential. For internal use only.",
    "show_page_numbers": True,
    "table_style": "striped",
}

PREFERENCES_DEFAULTS = {
    "theme_mode": "system",
    "accent_color": "emerald",
    "font_family": "inter",
}


def _hex_color(value: str, field: str) -> str:
    text = value.strip()
    if not text.startswith("#") or len(text) != 7 or any(
        c not in "0123456789abcdefABCDEF" for c in text[1:]
    ):
        raise ValidationFailedError(f"{field} must be a hex color like #0f766e.")
    return text.upper()


def _merge_setting(db: Session, key: str, defaults: dict) -> dict:
    row = db.scalar(select(AppSetting).where(AppSetting.key == key))
    stored = dict(row.value) if row is not None else {}
    return {**defaults, **{k: v for k, v in stored.items() if k in defaults}}


def _save_setting(db: Session, key: str, value: dict) -> None:
    row = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def get_org_settings(db: Session) -> dict:
    return _merge_setting(db, "org", ORG_DEFAULTS)


def update_org_settings(db: Session, patch: dict, actor: User | None, request_id: str | None) -> dict:
    current = get_org_settings(db)
    if "org_name" in patch and patch["org_name"] is not None:
        name = str(patch["org_name"]).strip()
        if not name or len(name) > 200:
            raise ValidationFailedError("Organization name must be 1 to 200 characters.")
        current["org_name"] = name
    if "org_tagline" in patch and patch["org_tagline"] is not None:
        tagline = str(patch["org_tagline"]).strip()
        if len(tagline) > 200:
            raise ValidationFailedError("Tagline must be 200 characters or fewer.")
        current["org_tagline"] = tagline
    _save_setting(db, "org", current)
    audit_service.record_audit_event(
        db,
        action="settings.updated",
        resource_type="settings",
        resource_id="org",
        actor=actor,
        request_id=request_id,
        change_summary="Organization settings updated",
        metadata={"fields": sorted(set(patch) & {"org_name", "org_tagline"})},
    )
    return current


def get_pdf_design(db: Session) -> dict:
    return _merge_setting(db, "pdf_design", PDF_DESIGN_DEFAULTS)


def _apply_pdf_patch(current: dict, patch: dict) -> tuple[dict, list[str]]:
    current = dict(current)
    changed = []
    if patch.get("paper_size") is not None:
        if patch["paper_size"] not in PAPER_SIZES:
            raise ValidationFailedError("Paper size must be A4 or Letter.")
        current["paper_size"] = patch["paper_size"]
        changed.append("paper_size")
    if patch.get("orientation") is not None:
        if patch["orientation"] not in ORIENTATIONS:
            raise ValidationFailedError("Orientation must be portrait or landscape.")
        current["orientation"] = patch["orientation"]
        changed.append("orientation")
    if patch.get("accent_color") is not None:
        current["accent_color"] = _hex_color(patch["accent_color"], "Accent color")
        changed.append("accent_color")
    if patch.get("font_family") is not None:
        if patch["font_family"] not in PDF_FONTS:
            raise ValidationFailedError("Font family must be sans, serif, or mono.")
        current["font_family"] = patch["font_family"]
        changed.append("font_family")
    if patch.get("font_size_pt") is not None:
        size = patch["font_size_pt"]
        if not isinstance(size, int) or not 7 <= size <= 12:
            raise ValidationFailedError("Font size must be between 7 and 12 points.")
        current["font_size_pt"] = size
        changed.append("font_size_pt")
    for key in ("show_cover_page", "header_show_logo", "header_show_org_name", "show_page_numbers"):
        if patch.get(key) is not None:
            if not isinstance(patch[key], bool):
                raise ValidationFailedError(f"{key} must be true or false.")
            current[key] = patch[key]
            changed.append(key)
    if patch.get("footer_text") is not None:
        text = str(patch["footer_text"]).strip()
        if len(text) > 200:
            raise ValidationFailedError("Footer text must be 200 characters or fewer.")
        current["footer_text"] = text
        changed.append("footer_text")
    if patch.get("table_style") is not None:
        if patch["table_style"] not in TABLE_STYLES:
            raise ValidationFailedError("Table style must be striped, plain, or bordered.")
        current["table_style"] = patch["table_style"]
        changed.append("table_style")
    return current, changed


def preview_pdf_design(db: Session, patch: dict) -> dict:
    """Validated draft without persisting (used for the design preview)."""
    draft, _ = _apply_pdf_patch(get_pdf_design(db), patch)
    return draft


def update_pdf_design(db: Session, patch: dict, actor: User | None, request_id: str | None) -> dict:
    current, changed = _apply_pdf_patch(get_pdf_design(db), patch)
    _save_setting(db, "pdf_design", current)
    if changed:
        audit_service.record_audit_event(
            db,
            action="settings.updated",
            resource_type="settings",
            resource_id="pdf_design",
            actor=actor,
            request_id=request_id,
            change_summary="PDF export design updated",
            metadata={"fields": sorted(changed)},
        )
    return current


def get_user_preferences(user: User) -> dict:
    stored = dict(user.preferences or {})
    return {**PREFERENCES_DEFAULTS, **{k: v for k, v in stored.items() if k in PREFERENCES_DEFAULTS}}


def update_user_preferences(db: Session, user: User, patch: dict) -> dict:
    current = get_user_preferences(user)
    if patch.get("theme_mode") is not None:
        if patch["theme_mode"] not in THEME_MODES:
            raise ValidationFailedError("Theme mode must be light, dark, or system.")
        current["theme_mode"] = patch["theme_mode"]
    if patch.get("accent_color") is not None:
        if patch["accent_color"] not in ACCENT_COLORS:
            raise ValidationFailedError("Unknown accent color.")
        current["accent_color"] = patch["accent_color"]
    if patch.get("font_family") is not None:
        if patch["font_family"] not in FONT_CHOICES:
            raise ValidationFailedError("Unknown font family.")
        current["font_family"] = patch["font_family"]
    user.preferences = current
    db.add(user)
    return current
