"""Settings schemas: organization profile, PDF export design, appearance."""

from pydantic import BaseModel, Field


class OrgSettingsOut(BaseModel):
    org_name: str
    org_tagline: str


class OrgSettingsUpdate(BaseModel):
    org_name: str | None = Field(default=None, min_length=1, max_length=200)
    org_tagline: str | None = Field(default=None, max_length=200)


class PdfDesignOut(BaseModel):
    paper_size: str
    orientation: str
    accent_color: str
    font_family: str
    font_size_pt: int
    show_cover_page: bool
    header_show_logo: bool
    header_show_org_name: bool
    footer_text: str
    show_page_numbers: bool
    table_style: str


class PdfDesignUpdate(BaseModel):
    paper_size: str | None = None
    orientation: str | None = None
    accent_color: str | None = Field(default=None, max_length=7)
    font_family: str | None = None
    font_size_pt: int | None = Field(default=None, ge=7, le=12)
    show_cover_page: bool | None = None
    header_show_logo: bool | None = None
    header_show_org_name: bool | None = None
    footer_text: str | None = Field(default=None, max_length=200)
    show_page_numbers: bool | None = None
    table_style: str | None = None


class PdfDesignPreviewRequest(BaseModel):
    design: PdfDesignUpdate


class UserPreferencesOut(BaseModel):
    theme_mode: str
    accent_color: str
    font_family: str


class UserPreferencesUpdate(BaseModel):
    theme_mode: str | None = None
    accent_color: str | None = None
    font_family: str | None = None
