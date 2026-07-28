"""Administrator policy library, integrated upload preview, and Bin."""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import html

import streamlit as st
from pydantic import ValidationError

from authentication.current_user import AuthenticatedUser
from config.settings import get_settings
from database.session import SessionFactory
from modules.documents.policy_file_parser import ALLOWED_POLICY_EXTENSIONS
from schemas.policy_schema import (
    PolicyMetadataUpdate,
    PolicyPermanentDeleteRequest,
    PolicyUploadRequest,
)
from services.policy_service import PolicyAdminView, PolicyService
from ui.components.data_table import render_admin_table
from ui.components.operation_feedback import (
    render_operation_feedback,
    set_operation_feedback,
)


MAX_INLINE_CONTENT_CHARACTERS = 100_000

_POLICY_UPLOAD_NONCE_STATE_KEY = "_policy_upload_nonce"
_POLICY_UPLOAD_WIDGET_PREFIX = "policy_upload_"


def _get_policy_upload_nonce() -> int:
    """Return the current upload-widget generation number."""

    raw_value = st.session_state.get(
        _POLICY_UPLOAD_NONCE_STATE_KEY,
        0,
    )

    try:
        nonce = max(0, int(raw_value))
    except (TypeError, ValueError):
        nonce = 0

    st.session_state[
        _POLICY_UPLOAD_NONCE_STATE_KEY
    ] = nonce

    return nonce


def _policy_upload_widget_key(
    nonce: int,
    name: str,
) -> str:
    """Build one upload widget key for the current generation."""

    normalized_name = (
        name.strip()
        .replace(" ", "_")
        .replace("-", "_")
    )

    return (
        f"{_POLICY_UPLOAD_WIDGET_PREFIX}"
        f"{nonce}_{normalized_name}"
    )


def _cleanup_old_policy_upload_state(
    active_nonce: int,
) -> None:
    """Remove upload-widget state from earlier completed uploads.

    Cleanup runs before the current generation's widgets are created.
    This avoids modifying an already-instantiated Streamlit widget.
    """

    active_prefix = (
        f"{_POLICY_UPLOAD_WIDGET_PREFIX}"
        f"{active_nonce}_"
    )

    stale_keys = [
        key
        for key in list(st.session_state.keys())
        if (
            isinstance(key, str)
            and key.startswith(
                _POLICY_UPLOAD_WIDGET_PREFIX
            )
            and not key.startswith(active_prefix)
        )
    ]

    for key in stale_keys:
        st.session_state.pop(key, None)


def _advance_policy_upload_state(
    current_nonce: int,
) -> None:
    """Switch the next rerun to a fresh upload-widget generation."""

    st.session_state[
        _POLICY_UPLOAD_NONCE_STATE_KEY
    ] = current_nonce + 1


_POLICY_VERSION_NONCE_PREFIX = "_policy_version_upload_nonce_"
_POLICY_VERSION_WIDGET_PREFIX = "policy_version_upload_"


def _get_policy_version_nonce(policy_id: int) -> int:
    """Return the current inline new-version uploader generation."""

    state_key = (
        f"{_POLICY_VERSION_NONCE_PREFIX}"
        f"{policy_id}"
    )
    raw_value = st.session_state.get(state_key, 0)

    try:
        nonce = max(0, int(raw_value))
    except (TypeError, ValueError):
        nonce = 0

    st.session_state[state_key] = nonce
    return nonce


def _policy_version_widget_key(
    policy_id: int,
    nonce: int,
    name: str,
) -> str:
    """Build a unique key for one managed-policy version uploader."""

    normalized_name = (
        name.strip()
        .replace(" ", "_")
        .replace("-", "_")
    )

    return (
        f"{_POLICY_VERSION_WIDGET_PREFIX}"
        f"{policy_id}_{nonce}_{normalized_name}"
    )


def _cleanup_policy_version_state(
    policy_id: int,
    active_nonce: int,
) -> None:
    """Remove stale widget state for this policy's old upload runs."""

    policy_prefix = (
        f"{_POLICY_VERSION_WIDGET_PREFIX}"
        f"{policy_id}_"
    )
    active_prefix = (
        f"{policy_prefix}"
        f"{active_nonce}_"
    )

    stale_keys = [
        key
        for key in list(st.session_state.keys())
        if (
            isinstance(key, str)
            and key.startswith(policy_prefix)
            and not key.startswith(active_prefix)
        )
    ]

    for key in stale_keys:
        st.session_state.pop(key, None)


def _advance_policy_version_state(
    policy_id: int,
    current_nonce: int,
) -> None:
    """Reset the inline new-version uploader after success."""

    st.session_state[
        f"{_POLICY_VERSION_NONCE_PREFIX}"
        f"{policy_id}"
    ] = current_nonce + 1


def _unique_preview_headings(
    sections,
) -> list[str]:
    """Return every unique heading in its original source order."""

    headings: list[str] = []
    seen: set[str] = set()

    for section in sections:
        heading = " ".join(
            str(section.heading or "").split()
        ).strip()

        if not heading:
            continue

        normalized = heading.casefold()

        if normalized in seen:
            continue

        seen.add(normalized)
        headings.append(heading)

    return headings


def _render_detected_headings(
    sections,
) -> None:
    """Render all headings as a compact wrapped numbered list."""

    headings = _unique_preview_headings(sections)

    if not headings:
        return

    items = "".join(
        (
            "<li style='margin:0 0 3px 0;"
            "line-height:1.28;overflow-wrap:anywhere;'>"
            f"{html.escape(heading)}"
            "</li>"
        )
        for heading in headings
    )

    st.markdown(
        (
            "<div style='background:#F8F9FC;"
            "border:1px solid #D8DEEA;border-radius:10px;"
            "padding:12px 14px;margin:5px 0 10px 0;'>"
            "<div style='font-weight:700;color:#10172A;"
            "margin-bottom:6px;'>"
            f"Detected headings ({len(headings)})"
            "</div>"
            "<ol style='margin:0;padding-left:22px;"
            "color:#10172A;line-height:1.28;'>"
            f"{items}</ol></div>"
        ),
        unsafe_allow_html=True,
    )


def _format_section_preview(
    sections,
) -> str:
    """Return all sections with a separator before each heading."""

    blocks: list[str] = []

    for index, section in enumerate(
        sections,
        start=1,
    ):
        heading = " ".join(
            str(
                section.heading
                or "Policy Details"
            ).split()
        ).strip()
        body = str(section.text or "").strip()
        page_label = (
            f" · Page {section.page_number}"
            if getattr(
                section,
                "page_number",
                None,
            )
            else ""
        )

        blocks.append(
            (
                f"{'─' * 56}\n"
                f"{index}. {heading}{page_label}\n"
                f"{body}"
            ).strip()
        )

    if blocks:
        blocks.append("─" * 56)

    return "\n".join(blocks)


def _policy_text_to_html(value: str) -> str:
    """Escape source text and preserve every line explicitly."""

    return (
        html.escape(value)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
    )


def _render_full_section_preview(
    sections,
) -> None:
    """Render every heading together with its own content.

    Explicit HTML breaks stop long text and blank lines from escaping the
    dark preview surface and inheriting the page's dark text color.
    """

    if not sections:
        st.info("No extracted policy content is available.")
        return

    section_cards: list[str] = []

    for index, section in enumerate(
        sections,
        start=1,
    ):
        heading = " ".join(
            str(
                section.heading
                or "Policy Details"
            ).split()
        ).strip()
        body = str(section.text or "").strip()
        page_label = (
            f" · Page {section.page_number}"
            if getattr(
                section,
                "page_number",
                None,
            )
            else ""
        )

        safe_heading = html.escape(
            f"{index}. {heading}{page_label}"
        )
        safe_body = _policy_text_to_html(body)

        section_cards.append(
            (
                "<section class='hr-policy-preview-section'>"
                "<div class='hr-policy-preview-heading'>"
                f"{safe_heading}"
                "</div>"
                "<div class='hr-policy-preview-content'>"
                f"{safe_body}"
                "</div>"
                "</section>"
            )
        )

    st.markdown("**Extracted Text Preview**")
    st.markdown(
        (
            "<div class='hr-policy-section-preview'>"
            f"{''.join(section_cards)}"
            "<div class='hr-policy-preview-final-line'></div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )



def _full_content_editor_height(
    content: str,
) -> int:
    """Estimate enough height to show the complete editable content.

    Long lines are counted as wrapped display lines. No maximum cap is used,
    so the administrator can review the entire content without an internal
    textarea scrollbar.
    """

    raw_lines = content.splitlines() or [""]
    display_lines = 0

    for line in raw_lines:
        display_lines += max(
            1,
            (len(line) + 124) // 125,
        )

    return max(
        520,
        86 + (display_lines * 19),
    )


def _format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "—"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_datetime(value) -> str:
    return PolicyService.format_datetime(
        value,
        get_settings().display_timezone,
    )


def _policy_id(policy) -> str:
    return PolicyService.public_id_for(policy)


def _filename_title(policy, document) -> str:
    if document is None:
        return policy.title
    return f"{document.original_filename}\n{policy.title}"


def _extracted_text_filename(view: PolicyAdminView) -> str:
    source_name = view.document.original_filename if view.document else view.policy.title
    return f"{Path(source_name).stem.strip() or 'policy'}_extracted_text.txt"


def _policy_rows(policies, document_map, *, include_bin_date: bool = False):
    rows = []
    for policy in policies:
        document = document_map.get(policy.id)
        row = {
            "Policy ID": _policy_id(policy),
            "Filename / Title": _filename_title(policy, document),
            "Category": policy.category,
            "Version": policy.version,
            "File Size": _format_size(document.size_bytes if document else None),
            "Date Uploaded": _format_datetime(policy.created_at),
        }
        if include_bin_date:
            row["Moved to Bin"] = _format_datetime(policy.trashed_at)
        rows.append(row)
    return rows


def _render_policy_table(policies, document_map, *, key: str, include_bin_date: bool = False) -> None:
    rows = _policy_rows(policies, document_map, include_bin_date=include_bin_date)
    if not rows:
        st.info("No policy versions are available in this section.")
        return
    widths = ("115px", "330px", "190px", "100px", "120px", "190px")
    if include_bin_date:
        widths = (*widths, "190px")
    render_admin_table(
        rows,
        key=key,
        min_width=1180 if not include_bin_date else 1340,
        column_widths=widths,
    )


def _render_overview(view: PolicyAdminView) -> None:
    policy, document = view.policy, view.document
    metrics = st.columns(4)
    metrics[0].metric("Policy ID", _policy_id(policy))
    metrics[1].metric("Version", policy.version)
    metrics[2].metric("Category", policy.category)
    metrics[3].metric("Sections", len(view.sections))

    rows = [
        {"Field": "Filename / Title", "Value": _filename_title(policy, document)},
        {"Field": "Date uploaded", "Value": _format_datetime(policy.created_at)},
        {"Field": "Library location", "Value": "Bin" if policy.status == "trashed" else "Policies"},
        {"Field": "Source type", "Value": "Uploaded file" if document else "Legacy manual entry"},
    ]
    render_admin_table(
        rows,
        key=f"policy-overview-{policy.id}",
        min_width=680,
        column_widths=("190px", "490px"),
        compact=True,
    )

    if document:
        render_admin_table(
            [
                {"Field": "Original filename", "Value": document.original_filename},
                {"Field": "File type", "Value": f"{document.file_extension.upper()} · {document.mime_type}"},
                {"Field": "File size", "Value": _format_size(document.size_bytes)},
                {"Field": "Page count", "Value": document.page_count or "Not available"},
                {"Field": "SHA-256", "Value": document.sha256},
            ],
            key=f"policy-file-{policy.id}",
            min_width=680,
            column_widths=("190px", "490px"),
            compact=True,
        )


def _render_extracted_content(view: PolicyAdminView) -> None:
    text = view.extracted_text or ""
    st.caption(f"{len(text):,} extracted characters")
    shown = text[:MAX_INLINE_CONTENT_CHARACTERS]
    if len(text) > MAX_INLINE_CONTENT_CHARACTERS:
        st.warning("The viewer is truncated. Download the complete extracted text below.")
    st.text_area(
        "Extracted Policy Content",
        value=shown,
        height=500,
        disabled=True,
        key=f"policy_content_{view.policy.id}",
    )
    st.download_button(
        "Download Complete Extracted Text",
        data=text.encode("utf-8"),
        file_name=_extracted_text_filename(view),
        mime="text/plain",
        use_container_width=True,
        key=f"download_extracted_{view.policy.id}",
    )


def _render_sections(view: PolicyAdminView) -> None:
    section_search = st.text_input(
        "Find in Sections",
        placeholder="Search a heading or extracted text...",
        key=f"section_search_{view.policy.id}",
    ).strip().lower()
    matches = [
        section
        for section in view.sections
        if (
            not section_search
            or section_search in section.heading.lower()
            or section_search in section.text.lower()
        )
    ]
    st.caption(f"Showing {len(matches)} of {len(view.sections)} sections")
    for section in matches:
        page = f" · Page {section.page_number}" if section.page_number else ""
        with st.expander(f"{section.sequence_number}. {section.heading}{page}"):
            st.write(section.text)


def _render_original_file(current_user: AuthenticatedUser, view: PolicyAdminView) -> None:
    if view.document is None:
        st.info("No original uploaded file exists for this legacy record.")
        return
    try:
        with SessionFactory() as session:
            download = PolicyService(session).get_policy_download(
                company_id=current_user.company_id,
                policy_id=view.policy.id,
                published_only=False,
            )
        st.download_button(
            "Download Original Policy File",
            data=download.data,
            file_name=download.filename,
            mime=download.mime_type,
            use_container_width=True,
            key=f"download_original_{view.policy.id}",
        )
    except (ValueError, FileNotFoundError) as error:
        st.error(str(error))


def _version_rows(current_user: AuthenticatedUser, title: str):
    with SessionFactory() as session:
        service = PolicyService(session)
        versions = service.repository.list_by_title(
            company_id=current_user.company_id,
            title=title,
        )
        documents = service.get_document_map(
            company_id=current_user.company_id,
            policies=versions,
        )
    rows = []
    for policy in versions:
        doc = documents.get(policy.id)
        rows.append({
            "Policy ID": _policy_id(policy),
            "Version": policy.version,
            "Filename": doc.original_filename if doc else "Legacy manual entry",
            "Date Uploaded": _format_datetime(policy.created_at),
            "Location": "Bin" if policy.status == "trashed" else "Policies",
        })
    return rows


def _render_version_history(current_user: AuthenticatedUser, view: PolicyAdminView) -> None:
    rows = _version_rows(current_user, view.policy.title)
    render_admin_table(
        rows,
        key=f"version-history-{view.policy.id}",
        min_width=900,
        column_widths=("120px", "100px", "300px", "190px", "110px"),
    )


def _render_move_to_bin(current_user: AuthenticatedUser, view: PolicyAdminView) -> None:
    public_id = _policy_id(view.policy)
    st.warning(
        "This keeps the file and all extracted content in the Bin. "
        "Employees and Policy Q&A will no longer see this version."
    )
    with st.form(f"move_policy_bin_{view.policy.id}"):
        confirmation = st.text_input(
            "Type the exact Policy ID to confirm",
            placeholder=public_id,
            max_chars=30,
        )
        submitted = st.form_submit_button(
            "Move Policy Version to Bin",
            use_container_width=True,
        )
    if submitted:
        try:
            with st.spinner("Moving policy version to Bin…"):
                with SessionFactory() as session:
                    moved = PolicyService(session).move_to_bin(
                        company_id=current_user.company_id,
                        policy_id=view.policy.id,
                        user_id=current_user.user_id,
                        confirmation_public_id=confirmation,
                    )
            set_operation_feedback(
                f"Moved {_policy_id(moved)} · {moved.title} v{moved.version} to Bin.",
                namespace="policy",
            )
            st.rerun()
        except ValueError as error:
            st.error(str(error))


def _render_upload(current_user: AuthenticatedUser, all_versions) -> None:
    settings = get_settings()

    upload_nonce = _get_policy_upload_nonce()
    _cleanup_old_policy_upload_state(upload_nonce)
    st.subheader("Upload Policy File")
    st.caption(
        "The filename becomes the policy title automatically. Category is "
        "suggested from file headings and remains editable. Every successful "
        "upload is published immediately."
    )
    uploaded = st.file_uploader(
        "Policy File *",
        type=[ext.lstrip(".") for ext in sorted(ALLOWED_POLICY_EXTENSIONS)],
        help=(
            f"Maximum size: {settings.policy_upload_max_mb} MB. "
            "Scanned image-only PDFs are not supported yet."
        ),
        key=_policy_upload_widget_key(
            upload_nonce,
            "file",
        ),
    )
    if uploaded is None:
        st.info("Choose a file to generate its title, category suggestion, version history, and preview.")
        return

    unique_titles = sorted({p.title for p in all_versions})
    mode = st.radio(
        "Version linking",
        options=[
            "Auto-detect from filename",
            "Select existing policy",
        ],
        horizontal=True,
        help=(
            "Auto-detect matches the cleaned filename. Select existing policy "
            "when the new file uses a different filename."
        ),
        key=_policy_upload_widget_key(
            upload_nonce,
            "version_linking",
        ),
    )
    selected_title = None
    if mode == "Select existing policy":
        if unique_titles:
            selected_title = st.selectbox(
                "Existing Policy",
                options=unique_titles,
                key=_policy_upload_widget_key(
                    upload_nonce,
                    "existing_policy",
                ),
            )
        else:
            st.info("No existing policy is available yet; filename auto-detection will be used.")

    try:
        with SessionFactory() as session:
            preview = PolicyService(session).preview_policy_upload(
                company_id=current_user.company_id,
                filename=uploaded.name,
                file_bytes=uploaded.getvalue(),
                maximum_size_bytes=settings.policy_upload_max_mb * 1024 * 1024,
                mime_type=uploaded.type,
                selected_existing_title=selected_title,
            )
    except ValueError as error:
        st.error(str(error))
        return

    fingerprint = hashlib.sha256(
        (preview.parsed.sha256 + preview.display_title).encode("utf-8")
    ).hexdigest()[:12]
    category_key = _policy_upload_widget_key(
        upload_nonce,
        f"category_{fingerprint}",
    )
    version_key = _policy_upload_widget_key(
        upload_nonce,
        f"version_{fingerprint}",
    )
    if category_key not in st.session_state:
        st.session_state[category_key] = preview.suggested_category
    if version_key not in st.session_state:
        st.session_state[version_key] = "1.0" if not preview.previous_versions else ""

    columns = st.columns(3)
    with columns[0]:
        st.text_input("Policy Filename / Title", value=preview.display_title, disabled=True)
    with columns[1]:
        category = st.text_input(
            "Category *",
            key=category_key,
            max_chars=100,
            help="Used for filtering and organizing Policy Q&A. The suggestion is editable.",
        )
    with columns[2]:
        version = st.text_input(
            "Version *",
            key=version_key,
            max_chars=30,
            placeholder="Example: 1.1",
            help="Manual input. Previous versions are shown below.",
        )

    st.text_input(
        "Date Uploaded",
        value=_format_datetime(datetime.now(timezone.utc)),
        disabled=True,
        help="The final date and time are recorded automatically when upload completes.",
    )

    if preview.previous_versions:
        st.markdown("**Previous versions**")
        render_admin_table(
            [
                {
                    "Policy ID": v.public_id,
                    "Version": v.version,
                    "Date Uploaded": _format_datetime(v.uploaded_at),
                    "Location": "Bin" if v.in_bin else "Policies",
                }
                for v in preview.previous_versions
            ],
            key=(
                f"upload-history-"
                f"{upload_nonce}-{fingerprint}"
            ),
            min_width=700,
            column_widths=("130px", "120px", "260px", "130px"),
            compact=True,
        )
    else:
        st.caption("No previous version was detected for this title.")

    with st.expander("Document Preview", expanded=True):
        st.caption(
            f"{len(preview.parsed.sections)} searchable sections · "
            f"{_format_size(preview.parsed.size_bytes)} · "
            f"{preview.parsed.original_filename}"
        )
        _render_detected_headings(
            preview.parsed.sections
        )
        _render_full_section_preview(
            preview.parsed.sections
        )

    if st.button(
        "Upload and Process Policy",
        type="primary",
        use_container_width=True,
        key=_policy_upload_widget_key(
            upload_nonce,
            "submit",
        ),
    ):
        try:
            request = PolicyUploadRequest(
                company_id=current_user.company_id,
                created_by_user_id=current_user.user_id,
                title=preview.display_title,
                category=category,
                version=version,
            )
            with st.spinner("Uploading, extracting, and publishing policy…"):
                with SessionFactory() as session:
                    policy = PolicyService(session).create_policy_from_upload(
                        values=request,
                        filename=uploaded.name,
                        file_bytes=uploaded.getvalue(),
                        mime_type=uploaded.type,
                        maximum_size_bytes=settings.policy_upload_max_mb * 1024 * 1024,
                    )
            # Use a new uploader/widget generation on the next rerun.
            # The selected file, generated preview, previous-version table,
            # category, version, and linking choice are therefore cleared.
            _advance_policy_upload_state(
                upload_nonce
            )

            set_operation_feedback(
                f"Uploaded and published {_policy_id(policy)} · {policy.title} v{policy.version}.",
                namespace="policy",
            )
            st.rerun()
        except ValidationError as error:
            st.error(error.errors()[0]["msg"])
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("The file could not be processed. Confirm that it is readable and supported.")


def _render_edit_policy_details(
    current_user: AuthenticatedUser,
    view: PolicyAdminView,
) -> None:
    """Edit family metadata and the selected version identifier."""

    policy = view.policy

    st.info(
        "Policy Title and Category apply to every version currently "
        "grouped under this policy. Version and Content apply only to "
        "the selected record. Saving Content regenerates the searchable "
        "sections used by Policy Q&A. The original uploaded file remains "
        "unchanged and can still be downloaded."
    )

    with st.form(
        f"edit_policy_metadata_{policy.id}"
    ):
        title = st.text_input(
            "Policy Title / Family Name *",
            value=policy.title,
            max_chars=200,
        )
        category = st.text_input(
            "Category *",
            value=policy.category,
            max_chars=100,
        )
        version = st.text_input(
            "Selected Version *",
            value=policy.version,
            max_chars=30,
        )
        content = st.text_area(
            "Editable Policy Content *",
            value=view.extracted_text,
            height=_full_content_editor_height(
                view.extracted_text
            ),
            help=(
                "This approved searchable text is used by the content "
                "viewer and Policy Q&A. Editing it does not replace "
                "the original uploaded file."
            ),
        )
        st.caption(
            "Saving content rebuilds searchable sections. Page-number "
            "references are removed because edited text may no longer "
            "match the original file pages exactly."
        )

        submitted = st.form_submit_button(
            "Save Policy Changes",
            type="primary",
            use_container_width=True,
        )

    if not submitted:
        return

    try:
        request = PolicyMetadataUpdate(
            company_id=current_user.company_id,
            policy_id=policy.id,
            title=title,
            category=category,
            version=version,
            content=content,
        )

        with st.spinner(
            "Saving policy details…"
        ):
            with SessionFactory() as session:
                updated = PolicyService(
                    session
                ).update_policy_metadata(request)

        set_operation_feedback(
            f"Updated {_policy_id(updated)} · "
            f"{updated.title} v{updated.version}.",
            namespace="policy",
        )
        st.rerun()

    except ValidationError as error:
        st.error(error.errors()[0]["msg"])
    except ValueError as error:
        st.error(str(error))


def _render_upload_new_version(
    current_user: AuthenticatedUser,
    view: PolicyAdminView,
) -> None:
    """Upload a new source file version for the selected policy family."""

    settings = get_settings()
    policy = view.policy
    nonce = _get_policy_version_nonce(policy.id)
    _cleanup_policy_version_state(
        policy.id,
        nonce,
    )

    st.info(
        f"Selected policy: {_policy_id(policy)} · "
        f"{policy.title} v{policy.version}. "
        "The new upload keeps the same policy family and creates "
        "a separate version record."
    )

    uploaded = st.file_uploader(
        "New Version Policy File *",
        type=[
            ext.lstrip(".")
            for ext in sorted(
                ALLOWED_POLICY_EXTENSIONS
            )
        ],
        help=(
            f"Maximum size: "
            f"{settings.policy_upload_max_mb} MB."
        ),
        key=_policy_version_widget_key(
            policy.id,
            nonce,
            "file",
        ),
    )

    if uploaded is None:
        st.caption(
            "Choose the replacement document for the new version. "
            "The current version remains unchanged."
        )
        return

    try:
        with SessionFactory() as session:
            preview = PolicyService(
                session
            ).preview_policy_upload(
                company_id=current_user.company_id,
                filename=uploaded.name,
                file_bytes=uploaded.getvalue(),
                maximum_size_bytes=(
                    settings.policy_upload_max_mb
                    * 1024
                    * 1024
                ),
                mime_type=uploaded.type,
                selected_existing_title=policy.title,
            )
    except ValueError as error:
        st.error(str(error))
        return

    fingerprint = hashlib.sha256(
        (
            preview.parsed.sha256
            + preview.display_title
        ).encode("utf-8")
    ).hexdigest()[:12]

    category_key = _policy_version_widget_key(
        policy.id,
        nonce,
        f"category_{fingerprint}",
    )
    version_key = _policy_version_widget_key(
        policy.id,
        nonce,
        f"version_{fingerprint}",
    )

    if category_key not in st.session_state:
        st.session_state[category_key] = (
            policy.category
        )

    if version_key not in st.session_state:
        st.session_state[version_key] = ""

    columns = st.columns(3)

    with columns[0]:
        st.text_input(
            "Policy Filename / Title",
            value=policy.title,
            disabled=True,
        )

    with columns[1]:
        category = st.text_input(
            "Category *",
            key=category_key,
            max_chars=100,
        )

    with columns[2]:
        version = st.text_input(
            "New Version *",
            key=version_key,
            max_chars=30,
            placeholder=(
                f"Latest: "
                f"{preview.latest_version or policy.version}"
            ),
        )

    st.text_input(
        "Date Uploaded",
        value=_format_datetime(
            datetime.now(timezone.utc)
        ),
        disabled=True,
    )

    st.markdown("**Existing version history**")
    render_admin_table(
        [
            {
                "Policy ID": item.public_id,
                "Version": item.version,
                "Date Uploaded": _format_datetime(
                    item.uploaded_at
                ),
                "Location": (
                    "Bin"
                    if item.in_bin
                    else "Policies"
                ),
            }
            for item in preview.previous_versions
        ],
        key=(
            f"managed-version-history-"
            f"{policy.id}-{nonce}-{fingerprint}"
        ),
        min_width=700,
        column_widths=(
            "130px",
            "120px",
            "260px",
            "130px",
        ),
        compact=True,
    )

    with st.expander(
        "New Version Document Preview",
        expanded=True,
    ):
        st.caption(
            f"{len(preview.parsed.sections)} searchable sections · "
            f"{_format_size(preview.parsed.size_bytes)} · "
            f"{preview.parsed.original_filename}"
        )
        _render_detected_headings(
            preview.parsed.sections
        )
        _render_full_section_preview(
            preview.parsed.sections
        )

    if not st.button(
        "Upload New Policy Version",
        type="primary",
        use_container_width=True,
        key=_policy_version_widget_key(
            policy.id,
            nonce,
            "submit",
        ),
    ):
        return

    try:
        request = PolicyUploadRequest(
            company_id=current_user.company_id,
            created_by_user_id=current_user.user_id,
            title=policy.title,
            category=category,
            version=version,
        )

        with st.spinner(
            "Uploading and publishing new policy version…"
        ):
            with SessionFactory() as session:
                created = PolicyService(
                    session
                ).create_policy_from_upload(
                    values=request,
                    filename=uploaded.name,
                    file_bytes=uploaded.getvalue(),
                    mime_type=uploaded.type,
                    maximum_size_bytes=(
                        settings.policy_upload_max_mb
                        * 1024
                        * 1024
                    ),
                )

        _advance_policy_version_state(
            policy.id,
            nonce,
        )
        set_operation_feedback(
            f"Uploaded new version "
            f"{_policy_id(created)} · "
            f"{created.title} v{created.version}.",
            namespace="policy",
        )
        st.rerun()

    except ValidationError as error:
        st.error(error.errors()[0]["msg"])
    except ValueError as error:
        st.error(str(error))
    except Exception:
        st.error(
            "The new policy version could not be processed."
        )


def _render_permanent_delete(
    current_user: AuthenticatedUser,
    view: PolicyAdminView,
) -> None:
    """Render the protected permanent-delete action for a Bin version."""

    policy = view.policy
    public_id = _policy_id(policy)

    st.error(
        "Permanent deletion cannot be undone. It removes this exact "
        "version, its original file, extracted text, and searchable "
        "sections. Other versions remain."
    )

    with st.form(
        f"permanent_delete_policy_{policy.id}"
    ):
        confirmation = st.text_input(
            "Type the exact Policy ID to confirm",
            placeholder=public_id,
            max_chars=30,
        )
        acknowledged = st.checkbox(
            "I understand that this policy version and its file "
            "will be permanently deleted.",
        )
        submitted = st.form_submit_button(
            "Delete Policy Version Permanently",
            use_container_width=True,
        )

    if not submitted:
        return

    try:
        request = PolicyPermanentDeleteRequest(
            company_id=current_user.company_id,
            policy_id=policy.id,
            confirmation_public_id=confirmation,
            permanent_delete_acknowledged=(
                acknowledged
            ),
        )

        with st.spinner(
            "Permanently deleting policy version…"
        ):
            with SessionFactory() as session:
                deleted = PolicyService(
                    session
                ).permanently_delete_from_bin(
                    request
                )

        set_operation_feedback(
            f"Permanently deleted "
            f"{deleted.public_id} · "
            f"{deleted.title} v{deleted.version}.",
            namespace="policy",
        )
        st.rerun()

    except ValidationError as error:
        st.error(error.errors()[0]["msg"])
    except ValueError as error:
        st.error(str(error))


def _render_manage(current_user: AuthenticatedUser, policies) -> None:
    st.divider()
    st.subheader("Manage Existing Policy")
    if not policies:
        st.info("Upload a policy before managing existing versions.")
        return
    options = {
        f"{_policy_id(p)} · {p.title} v{p.version}": p.id
        for p in policies
    }
    selected_label = st.selectbox("Select Policy", options=list(options))
    selected_id = options[selected_label]
    try:
        with SessionFactory() as session:
            view = PolicyService(session).get_admin_policy_view(
                company_id=current_user.company_id,
                policy_id=selected_id,
            )
    except ValueError as error:
        st.error(str(error)); return

    tabs = st.tabs([
        "Overview",
        "Edit Details",
        "Upload New Version",
        "Extracted Content",
        "Searchable Sections",
        "Original File",
        "Version History",
        "Move to Bin",
    ])
    with tabs[0]:
        _render_overview(view)
    with tabs[1]:
        _render_edit_policy_details(
            current_user,
            view,
        )
    with tabs[2]:
        _render_upload_new_version(
            current_user,
            view,
        )
    with tabs[3]:
        _render_extracted_content(view)
    with tabs[4]:
        _render_sections(view)
    with tabs[5]:
        _render_original_file(
            current_user,
            view,
        )
    with tabs[6]:
        _render_version_history(
            current_user,
            view,
        )
    with tabs[7]:
        _render_move_to_bin(
            current_user,
            view,
        )


def _render_bin(current_user: AuthenticatedUser, policies, document_map) -> None:
    st.subheader("Policy Bin")
    st.caption(
        "Bin versions are retained for history and can be restored. "
        "They are excluded from employee search, downloads, and Policy Q&A."
    )
    _render_policy_table(
        policies,
        document_map,
        key="policy-bin-list",
        include_bin_date=True,
    )
    if not policies:
        return
    options = {f"{_policy_id(p)} · {p.title} v{p.version}": p.id for p in policies}
    selected_label = st.selectbox("Select Bin Policy", options=list(options))
    selected_id = options[selected_label]
    with SessionFactory() as session:
        view = PolicyService(session).get_admin_policy_view(
            company_id=current_user.company_id,
            policy_id=selected_id,
        )
    tabs = st.tabs([
        "Overview",
        "Extracted Content",
        "Original File",
        "Version History",
        "Restore",
        "Delete Permanently",
    ])
    with tabs[0]:
        _render_overview(view)
    with tabs[1]:
        _render_extracted_content(view)
    with tabs[2]:
        _render_original_file(
            current_user,
            view,
        )
    with tabs[3]:
        _render_version_history(
            current_user,
            view,
        )
    with tabs[4]:
        st.info(
            "Restore returns this exact version to the active "
            "Policies library."
        )
        if st.button(
            "Restore Policy Version",
            type="primary",
            use_container_width=True,
        ):
            try:
                with st.spinner(
                    "Restoring policy version…"
                ):
                    with SessionFactory() as session:
                        restored = PolicyService(
                            session
                        ).restore_from_bin(
                            company_id=current_user.company_id,
                            policy_id=selected_id,
                        )
                set_operation_feedback(
                    f"Restored {_policy_id(restored)} · "
                    f"{restored.title} v{restored.version}.",
                    namespace="policy",
                )
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    with tabs[5]:
        _render_permanent_delete(
            current_user,
            view,
        )


def render_admin_policies_page(current_user: AuthenticatedUser) -> None:
    """Render active policies, integrated upload preview, and Bin."""

    st.title("Policies")
    st.caption(
        "Upload and preview policy files, track every version, and retain "
        "removed versions safely in the Bin."
    )
    render_operation_feedback(namespace="policy")

    with SessionFactory() as session:
        service = PolicyService(session)
        active = service.list_for_admin(current_user.company_id)
        bin_policies = service.list_bin(current_user.company_id)
        all_versions = service.list_all_versions(current_user.company_id)
        active_documents = service.get_document_map(
            company_id=current_user.company_id,
            policies=active,
        )
        bin_documents = service.get_document_map(
            company_id=current_user.company_id,
            policies=bin_policies,
        )

    policies_tab, bin_tab = st.tabs(["Policies", f"Bin ({len(bin_policies)})"])
    with policies_tab:
        _render_policy_table(active, active_documents, key="policy-list")
        _render_upload(current_user, all_versions)
        _render_manage(current_user, active)
    with bin_tab:
        _render_bin(current_user, bin_policies, bin_documents)
