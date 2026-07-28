"""Regression tests for clearing a successful policy upload."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    """Read the administrator Policies page source."""

    return (
        PROJECT_ROOT
        / "ui/pages/admin/policies_page.py"
    ).read_text(encoding="utf-8")


def test_upload_uses_generation_specific_file_key() -> None:
    """The uploader must remount after a successful transaction."""

    source = _source()

    assert '_POLICY_UPLOAD_NONCE_STATE_KEY' in source
    assert '_POLICY_UPLOAD_WIDGET_PREFIX' in source
    assert 'def _policy_upload_widget_key(' in source
    assert (
        'key=_policy_upload_widget_key(\n'
        '            upload_nonce,\n'
        '            "file",'
        in source
    )


def test_all_generated_upload_controls_share_the_nonce() -> None:
    """Stateful upload controls must reset together with the file."""

    source = _source()

    for name in [
        '"version_linking"',
        '"existing_policy"',
        'f"category_{fingerprint}"',
        'f"version_{fingerprint}"',
        '"submit"',
    ]:
        assert name in source

    assert "upload-history-" in source
    assert "f\"{upload_nonce}-{fingerprint}\"" in source


def test_success_advances_state_before_rerun() -> None:
    """The reset generation must advance only after upload succeeds."""

    source = _source()

    success_position = source.index(
        "_advance_policy_upload_state("
    )
    feedback_position = source.index(
        "set_operation_feedback(",
        success_position,
    )
    rerun_position = source.index(
        "st.rerun()",
        feedback_position,
    )

    assert success_position < feedback_position < rerun_position


def test_validation_errors_do_not_advance_upload_state() -> None:
    """Failed uploads must retain the selected file for correction."""

    source = _source()

    upload_start = source.index(
        'if st.button(\n'
        '        "Upload and Process Policy"'
    )
    upload_end = source.index(
        "\n\ndef _render_manage(",
        upload_start,
    )
    upload_block = source[upload_start:upload_end]

    assert upload_block.count(
        "_advance_policy_upload_state("
    ) == 1

    advance_position = upload_block.index(
        "_advance_policy_upload_state("
    )
    validation_position = upload_block.index(
        "except ValidationError"
    )
    value_error_position = upload_block.index(
        "except ValueError"
    )

    assert advance_position < validation_position
    assert advance_position < value_error_position


def test_old_upload_widget_keys_are_cleaned_before_render() -> None:
    """Previous generations must not accumulate in session state."""

    source = _source()

    assert "def _cleanup_old_policy_upload_state(" in source
    assert "st.session_state.pop(key, None)" in source

    upload_start = source.index(
        "def _render_upload("
    )
    uploader_position = source.index(
        "st.file_uploader(",
        upload_start,
    )
    cleanup_position = source.index(
        "_cleanup_old_policy_upload_state(upload_nonce)",
        upload_start,
    )

    assert cleanup_position < uploader_position


def test_upload_empty_state_returns_after_successful_reset() -> None:
    """A fresh uploader must hide preview controls until another file."""

    source = _source()

    assert "if uploaded is None:" in source
    assert (
        "Choose a file to generate its title, category suggestion, "
        "version history, and preview."
        in source
    )
    assert "_advance_policy_upload_state(" in source
