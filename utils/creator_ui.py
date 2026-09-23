"""Standalone, session-local creator UI. No discovery, AI or database calls."""

from hashlib import sha256
from io import BytesIO

import streamlit as st

from utils.creator import (CreatorDraft, CreatorError, MAX_CAPTIONS, MAX_TEXT_LENGTH,
                           MIN_FONT_SIZE, MAX_FONT_SIZE, MAX_OUTLINE_WIDTH, MAX_IMAGE_LAYERS)
from utils.rendering import render_draft, RenderingError


def open_creator():
    st.session_state.creator_active = True


def open_template_creator(template, preview):
    """Initialize the existing editor from the exact selected result image."""
    try:
        draft = CreatorDraft.from_bytes(preview)
    except Exception:
        st.session_state.library_notice = "Template image unavailable. Please try another template."
        return
    clear_creator()
    st.session_state.creator_draft = draft
    st.session_state.creator_source_digest = sha256(preview).hexdigest()
    st.session_state.creator_template = {"id": template["id"], "name": template["name"]}


def close_creator():
    st.session_state.creator_active = False


def clear_creator():
    generation = st.session_state.get("creator_generation", 0) + 1
    for key in list(st.session_state):
        if key.startswith("creator_"):
            del st.session_state[key]
    st.session_state.creator_generation = generation
    st.session_state.creator_active = True


def _invalidate_render():
    for key in ("creator_render", "creator_render_key"):
        st.session_state.pop(key, None)


def _upload_changed():
    # A missing widget after navigation is different from explicit file removal.
    st.session_state.creator_upload_changed = True


def caption_key(caption_id, field):
    generation = st.session_state.get("creator_generation", 0)
    return f"creator_caption_{generation}_{caption_id}_{field}"


def _edit_caption(caption_id, field):
    key = caption_key(caption_id, field)
    value = st.session_state[key]
    if field in ("x", "y", "width"):
        value /= 100
    errors = dict(st.session_state.get("creator_errors", {}))
    _invalidate_render()
    try:
        st.session_state.creator_draft = st.session_state.creator_draft.update_caption(
            caption_id, **{field: value})
        errors.pop(key, None)
    except CreatorError as error:
        errors[key] = f"Caption {caption_id}: {error}"
    st.session_state.creator_errors = errors


def _add_caption():
    try:
        st.session_state.creator_draft = st.session_state.creator_draft.add_caption()
        _invalidate_render()
    except CreatorError as error:
        st.session_state.creator_notice = str(error)


def _remove_caption(caption_id):
    st.session_state.creator_draft = st.session_state.creator_draft.remove_caption(caption_id)
    prefix = caption_key(caption_id, "")
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]
    st.session_state.creator_errors = {
        key: value for key, value in st.session_state.get("creator_errors", {}).items()
        if not key.startswith(prefix)}
    _invalidate_render()


def _accept_upload(uploaded):
    changed = st.session_state.pop("creator_upload_changed", False)
    if uploaded is None:
        if changed:
            clear_creator()
            st.rerun()
        return
    content = uploaded.getvalue()
    digest = sha256(content).hexdigest()
    if digest == st.session_state.get("creator_source_digest"):
        return
    # Remove former output/widgets before accepting a replacement, even on failure.
    _invalidate_render()
    image_epoch = st.session_state.get("creator_image_epoch", 0) + 1
    for key in list(st.session_state):
        if key.startswith(("creator_caption_", "creator_image_")):
            del st.session_state[key]
    st.session_state.creator_image_epoch = image_epoch
    for key in ("creator_draft", "creator_errors", "creator_source_error"):
        st.session_state.pop(key, None)
    st.session_state.creator_source_digest = digest
    st.session_state.pop("creator_template", None)
    try:
        # The model delegates to the shared V3 upload validator. Do not retain the
        # original filename or raw bytes in additional session-state fields.
        st.session_state.creator_draft = CreatorDraft.from_bytes(content)
    except CreatorError as error:
        st.session_state.creator_source_error = str(error)


def _caption_controls(caption):
    def options(field):
        key = caption_key(caption.id, field)
        value = getattr(caption, field)
        st.session_state.setdefault(key, value * 100 if field in ("x", "y", "width") else value)
        return dict(key=key, on_change=_edit_caption, args=(caption.id, field))

    with st.expander(f"Caption {caption.id}", expanded=True):
        st.text_area("Text", max_chars=MAX_TEXT_LENGTH, **options("text"))
        st.slider("X position (%)", 0.0, 100.0, step=1.0, **options("x"))
        st.slider("Y position (%)", 0.0, 100.0, step=1.0, **options("y"))
        st.slider("Text-box width (%)", 1.0, 100.0, step=1.0, **options("width"))
        st.slider("Font size (pixels)", MIN_FONT_SIZE, MAX_FONT_SIZE, **options("font_size"))
        st.selectbox("Alignment", ["left", "center", "right"], **options("alignment"))
        st.color_picker("Text color", **options("fill_color"))
        st.color_picker("Outline color", **options("outline_color"))
        st.slider("Outline width (pixels)", 0, MAX_OUTLINE_WIDTH, **options("outline_width"))
        st.button(f"Remove caption {caption.id}", key=caption_key(caption.id, "remove"),
                  on_click=_remove_caption, args=(caption.id,))


def image_key(layer_id, field):
    generation = st.session_state.get("creator_generation", 0)
    epoch = st.session_state.get("creator_image_epoch", 0)
    return f"creator_image_{generation}_{epoch}_{layer_id}_{field}"


def _add_image():
    if len(st.session_state.creator_draft.image_layers) < MAX_IMAGE_LAYERS:
        st.session_state.creator_image_pending = True
        _invalidate_render()


def _remove_image(layer_id):
    draft = st.session_state.creator_draft
    if any(layer.id == layer_id for layer in draft.image_layers):
        st.session_state.creator_draft = draft.remove_image_layer(layer_id)
    else:
        st.session_state.pop("creator_image_pending", None)
    prefix = image_key(layer_id, "")
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]
    st.session_state.creator_errors = {key: value for key, value in
        st.session_state.get("creator_errors", {}).items() if not key.startswith(prefix)}
    _invalidate_render()


def _image_display_value(layer, field):
    value = getattr(layer, field)
    if field in ("x", "y", "width", "height"):
        return round(float(value) * 100, 10)
    return float(value) if field == "rotation" else value


def _edit_image(layer_id, field, source_key=None):
    key = image_key(layer_id, field)
    value = st.session_state[source_key or key]
    if field in ("x", "y", "width", "height"):
        value /= 100
    errors = dict(st.session_state.get("creator_errors", {}))
    _invalidate_render()
    try:
        st.session_state.creator_draft = st.session_state.creator_draft.update_image_layer(layer_id, **{field: value})
        if field != "fit":
            layer = next(layer for layer in st.session_state.creator_draft.image_layers if layer.id == layer_id)
            # Callbacks run before widgets are instantiated. Synchronize from the
            # validated model here, never by assigning widget state after rendering.
            display = _image_display_value(layer, field)
            st.session_state[key] = display
            st.session_state[image_key(layer_id, field + "_number")] = display
        errors.pop(key, None)
    except CreatorError as error:
        errors[key] = f"Image {layer_id}: {error}"
    st.session_state.creator_errors = errors


def _image_upload_changed(layer_id):
    st.session_state[image_key(layer_id, "changed")] = True


def _new_image_position(draft):
    # All model defaults share a box. Stagger UI additions so the next opaque
    # image does not completely conceal the previous image and look like a
    # replacement. This is generic placement, unrelated to template slots.
    occupied = {(round(layer.x, 2), round(layer.y, 2)) for layer in draft.image_layers}
    for offset in range(MAX_IMAGE_LAYERS):
        position = round(0.1 + offset * 0.08, 2)
        if (position, position) not in occupied:
            return position, position
    return 0.1, 0.1


def _accept_image(uploaded, layer_id, pending):
    changed = st.session_state.pop(image_key(layer_id, "changed"), False)
    if uploaded is None:
        if changed and not pending:
            _remove_image(layer_id)
            st.rerun()
        return
    content = uploaded.getvalue()
    digest_key = image_key(layer_id, "digest")
    digest = sha256(content).hexdigest()
    if digest == st.session_state.get(digest_key):
        return
    st.session_state[digest_key] = digest
    _invalidate_render()
    error_key = image_key(layer_id, "upload")
    errors = dict(st.session_state.get("creator_errors", {}))
    try:
        draft = st.session_state.creator_draft
        x, y = _new_image_position(draft)
        st.session_state.creator_draft = (draft.add_image_layer(content, source_label=f"Image {layer_id}", x=x, y=y)
            if pending else draft.replace_image_layer(layer_id, content))
        errors.pop(error_key, None)
        st.session_state.creator_errors = errors
        if pending:
            st.session_state.pop("creator_image_pending", None)
        st.rerun()
    except CreatorError as error:
        errors[error_key] = f"Image {layer_id}: {error}"
        st.session_state.creator_errors = errors


def _image_numeric_control(layer, field, label, minimum, maximum):
    slider_key = image_key(layer.id, field)
    number_key = image_key(layer.id, field + "_number")
    value = _image_display_value(layer, field)
    st.session_state.setdefault(slider_key, value)
    st.session_state.setdefault(number_key, value)
    step = 1 if field == "opacity" else 1.0
    slider_column, number_column = st.columns([3, 1], vertical_alignment="bottom")
    with slider_column:
        st.slider(label, minimum, maximum, step=step, key=slider_key,
                  on_change=_edit_image, args=(layer.id, field, slider_key))
    with number_column:
        st.number_input(label + " value", min_value=minimum, max_value=maximum,
                        step=step, format="%d" if field == "opacity" else "%g",
                        key=number_key, label_visibility="collapsed",
                        on_change=_edit_image, args=(layer.id, field, number_key))


def _image_controls(layer_id, layer=None):
    def options(field):
        key = image_key(layer_id, field)
        value = getattr(layer, field)
        if field in ("x", "y", "width", "height"):
            value *= 100
        if field == "rotation":
            value = float(value)
        st.session_state.setdefault(key, value)
        return dict(key=key, on_change=_edit_image, args=(layer_id, field))

    # Key the panel as well as its widgets so removing a sibling cannot make the
    # browser reuse a positional panel for a different stable image ID.
    with st.container(key=image_key(layer_id, "panel")), st.expander(f"Image {layer_id}", expanded=True):
        uploaded = st.file_uploader(f"Upload image {layer_id}", type=["png", "jpg", "jpeg", "webp"],
            key=image_key(layer_id, "upload"), on_change=_image_upload_changed, args=(layer_id,))
        _accept_image(uploaded, layer_id, pending=layer is None)
        if layer is not None:
            st.image(BytesIO(layer.image_png), width=120, caption=f"Source for Image {layer_id}")
            st.caption("Upload another file here to replace this image and keep its placement.")
            for field, label, low in (("x", "X position (%)", -100.0), ("y", "Y position (%)", -100.0),
                                      ("width", "Width (%)", 1.0), ("height", "Height (%)", 1.0)):
                _image_numeric_control(layer, field, label, low, 100.0)
            st.selectbox("Fit mode", ["contain", "cover"], format_func=str.title, **options("fit"))
            _image_numeric_control(layer, "rotation", "Rotation (degrees)", -180.0, 180.0)
            _image_numeric_control(layer, "opacity", "Opacity (%)", 0, 100)
        st.button(f"Remove image {layer_id}", key=image_key(layer_id, "remove"),
                  on_click=_remove_image, args=(layer_id,))


def render_creator():
    st.title("Create a meme")
    if template := st.session_state.get("creator_template"):
        st.text("Selected template: " + template["name"])
    st.caption("Upload a base image, add images and captions, and download your finished meme.")
    st.caption("Images and captions stay in this session on the app's machine. "
               "On a hosted app, processing runs on the Streamlit server. "
               "Creation does not use OCR or your saved library.")
    st.button("Back to browsing", key="creator_back", on_click=close_creator)
    with st.container(key="creator_source"):
        generation = st.session_state.get("creator_generation", 0)
        uploaded = st.file_uploader("Creator image", type=["png", "jpg", "jpeg", "webp"],
                                    key=f"creator_upload_{generation}", on_change=_upload_changed)
        st.caption("PNG, JPEG or static WebP; up to 10 MB and 20 megapixels. "
                   "Images are normalized to at most 1600 pixels per side; transparency becomes white.")
        st.button("Clear creator", key="creator_clear", on_click=clear_creator)
        _accept_upload(uploaded)
        if st.session_state.get("creator_source_error"):
            st.error(st.session_state.creator_source_error)
        draft = st.session_state.get("creator_draft")
        if draft is None:
            st.info("Upload an image to start creating.")
            return
        with st.expander("Normalized source image", expanded=False):
            st.image(BytesIO(draft.base_png), use_container_width=True)
            st.caption(f"{draft.width} × {draft.height} pixels")

    with st.container(key="creator_editor"):
        controls, preview = st.columns([1, 1.4], gap="large")
        with controls:
            st.subheader("Images")
            st.caption("Images draw in the order shown, below all captions. Rotation is counterclockwise "
                       "around the box center. Contain shows the whole image; Cover center-crops it.")
            pending = st.session_state.get("creator_image_pending", False)
            st.button("Add image", key="creator_add_image", on_click=_add_image,
                      disabled=pending or len(draft.image_layers) >= MAX_IMAGE_LAYERS)
            st.caption(f"{len(draft.image_layers)} / {MAX_IMAGE_LAYERS} image layers")
            for layer in draft.image_layers:
                _image_controls(layer.id, layer)
            if pending:
                _image_controls(draft.next_image_id)
            st.subheader("Captions")
            st.caption("Position is the text box's top-left corner. Captions draw in the order shown. "
                       "The included font primarily supports Latin text.")
            st.button("Add caption", key="creator_add", on_click=_add_caption,
                      disabled=len(draft.captions) >= MAX_CAPTIONS)
            st.caption(f"{len(draft.captions)} / {MAX_CAPTIONS} captions")
            if notice := st.session_state.pop("creator_notice", None):
                st.warning(notice)
            for caption in draft.captions:
                _caption_controls(caption)
        with preview, st.container(key="creator_preview"):
            st.subheader("Live preview")
            st.caption("Preview updates when you apply a text edit or change a control.")
            if pending:
                _invalidate_render()
                st.info("Upload the pending image or remove it to continue previewing and exporting.")
            errors = st.session_state.get("creator_errors", {})
            if errors:
                _invalidate_render()
                for message in errors.values():
                    st.error(message)
                return
            if pending:
                return
            render_key = (draft.digest, draft.captions, draft.image_layers)
            if st.session_state.get("creator_render_key") != render_key:
                _invalidate_render()
                try:
                    result = render_draft(draft)
                except RenderingError as error:
                    st.error(str(error))
                    return
                st.session_state.creator_render = result
                st.session_state.creator_render_key = render_key
            result = st.session_state.creator_render
            st.image(BytesIO(result.png), use_container_width=True)
            if result.overflow_caption_ids:
                affected = ", ".join(f"Caption {cid}" for cid in result.overflow_caption_ids)
                st.warning(f"Clipped text: {affected}. Adjust position, box width or font size. "
                           "Your selected font sizes have been kept.")
            st.download_button("Download PNG", data=result.png, file_name="meme.png",
                               mime="image/png", key="creator_download_png")
