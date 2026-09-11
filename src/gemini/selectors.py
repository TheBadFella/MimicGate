"""
Centralized DOM selectors for Google Gemini (gemini.google.com).

Derived from live browser DOM and accessibility tree captures via DevTools MCP.
All selectors live here so when Gemini updates its UI, we only change this one file.
Each entry is a list of fallback selectors, tried in order until one matches.
"""

from __future__ import annotations


class GeminiSelectors:
    """CSS / Playwright selectors for gemini.google.com UI elements."""

    # -- Chat input ----------------------------------------------
    # Gemini uses a Quill-based rich-textarea with contenteditable div.
    CHAT_INPUT = [
        "div.ql-editor.textarea[contenteditable='true']",
        "rich-textarea div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true'][role='textbox'][aria-label*='prompt' i]",
        "div[contenteditable='true'][data-placeholder='Ask Gemini']",
        "rich-textarea .ql-editor",
        "rich-textarea",
    ]

    # -- Send button ---------------------------------------------
    # When text is entered into the editor, the voice/dictate button transitions into send.
    SEND_BUTTON = [
        "gem-icon-button.send-button.submit button:not([aria-label*='Stop' i])",
        "gem-icon-button.send-button.has-input button:not([aria-label*='Stop' i])",
        "button[aria-label*='Send message' i]",
        "div[data-test-id='send-button-container'] button:not([aria-label*='Stop' i])",
        "gem-icon-button.send-button button:not([aria-label*='Stop' i])",
        "button[aria-label*='Send prompt' i]",
        "button[aria-label*='Send' i]",
        "button:has(mat-icon[data-mat-icon-name='arrow_upward']):not([aria-label*='Stop' i])",
        "button:has(mat-icon[fonticon='arrow_upward']):not([aria-label*='Stop' i])",
        "button:has(mat-icon[data-mat-icon-name='send']):not([aria-label*='Stop' i])",
        "button:has(mat-icon[fonticon='send']):not([aria-label*='Stop' i])",
        "button.send-button:not([aria-label*='Stop' i])",
    ]

    # -- Voice / Dictate button (visible when composer is empty) --
    DICTATE_BUTTON = [
        "speech-dictation-mic-button button",
        "button[aria-label*='Dictate' i]",
        "button:has(mat-icon[data-mat-icon-name='mic'])",
    ]

    # -- Streaming / stop button (visible while generating) ------
    STOP_BUTTON = [
        "button[aria-label*='Stop response' i]",
        "button[aria-label*='Stop generating' i]",
        "button[aria-label*='Stop' i]",
        "button:has(mat-icon[data-mat-icon-name='stop'])",
        "button.stop-button",
    ]

    # -- Model / Mode selector -----------------------------------
    # Gemini uses <bard-mode-switcher> with button[data-test-id="bard-mode-menu-button"].
    # The active model label is displayed in span.picker-primary-text ("Flash", "3.8 Flash", "3.1 Pro", etc.).
    MODEL_SWITCHER_BUTTON = [
        "button[data-test-id='bard-mode-menu-button']",
        "bard-mode-switcher button.input-area-switch",
        "bard-mode-switcher button",
        "button[aria-label*='mode picker' i]",
    ]

    CURRENT_MODEL_LABEL = [
        "bard-mode-switcher span.picker-primary-text",
        "button[data-test-id='bard-mode-menu-button'] .picker-primary-text",
        "bard-mode-switcher .input-area-switch-label",
    ]

    MODEL_MENU_PANEL = [
        "div.mat-mdc-menu-panel",
        "div[role='menu']",
    ]

    MODEL_MENU_ITEMS = [
        "div.mat-mdc-menu-panel button.mat-mdc-menu-item",
        "div.mat-mdc-menu-panel [role='menuitem']",
        "button.mat-mdc-menu-item",
        "[role='menuitem']",
    ]

    # -- Assistant response messages -----------------------------
    # Gemini wraps assistant turns in <model-response>.
    ASSISTANT_MESSAGE = [
        "model-response",
        "div.response-container",
        "div.static-chat-experience-response-container",
    ]

    # -- Markdown content inside assistant message ---------------
    ASSISTANT_MARKDOWN = [
        "model-response message-content markdown",
        "model-response markdown",
        "model-response .markdown",
        "model-response message-content",
        "model-response .model-response-text",
    ]

    # -- User message --------------------------------------------
    USER_MESSAGE = [
        "user-query",
        "div.user-query-container",
        "[data-test-id='luminous-collapsed-bubble']",
    ]

    # -- Action buttons on completed assistant turn --------------
    COPY_BUTTON = [
        "button[aria-label*='Copy prompt' i]",
        "button[aria-label*='Copy response' i]",
        "button[aria-label*='Copy' i]",
        "button:has(mat-icon[data-mat-icon-name='content_copy'])",
    ]

    RETRY_BUTTON = [
        "button[aria-label*='Modify response' i]",
        "button[aria-label*='Retry' i]",
        "button[aria-label*='Regenerate' i]",
    ]

    # -- New chat ------------------------------------------------
    NEW_CHAT_BUTTON = [
        "gem-nav-list-item[data-test-id='new-chat-button'] a",
        "a[data-test-id='side-nav-sparkle-button']",
        "a[aria-label*='New chat' i]",
        "button[aria-label*='New chat' i]",
        "a[href='/app']",
    ]

    # -- Sidebar conversation links ------------------------------
    # -- Sidebar toggle / drawer buttons -------------------------
    SIDEBAR_TOGGLE_BUTTON = [
        "button[aria-label*='Main menu' i]",
        "button[aria-label*='Expand menu' i]",
        "button[data-test-id='side-nav-button']",
        "button:has(mat-icon[data-mat-icon-name='menu'])",
        "button:has(mat-icon:has-text('menu'))",
    ]

    # -- Sidebar conversation links & items ----------------------
    SIDEBAR_THREAD_LINKS = [
        "a[href^='/app/']",
        "a[href*='/app/']",
        "gem-nav-list-item a[href*='/app/']",
    ]

    SIDEBAR_THREAD_ITEM = [
        "gem-nav-list-item:has(a[href*='/app/'])",
        "div[data-test-id*='conversation']:has(a[href*='/app/'])",
        "a[href^='/app/']",
        "a[href*='/app/']",
    ]

    # Three-dot / overflow menu button on a conversation row
    SIDEBAR_THREAD_MENU_BUTTON = [
        "conversation-action-menu button",
        "button[aria-label*='actions' i]",
        "button[aria-label*='More options' i]",
        "button[aria-label*='options' i]",
        "button:has(mat-icon[data-mat-icon-name='more_vert'])",
        "button:has(mat-icon:has-text('more_vert'))",
        "button[aria-haspopup='menu']",
    ]

    # "Delete" choice in the conversation context menu
    THREAD_DELETE_OPTION = [
        "[role='menuitem']:has-text('Delete')",
        "button[role='menuitem']:has-text('Delete')",
        "button:has-text('Delete')",
        "button[aria-label*='Delete' i]",
        "div[role='menu'] button:has-text('Delete')",
        "div[role='menu'] [role='menuitem']:has-text('Delete')",
    ]

    # Confirm-delete action in the modal dialog
    THREAD_CONFIRM_DELETE_BUTTON = [
        "mat-dialog-container button:has-text('Delete')",
        "div[role='dialog'] button:has-text('Delete')",
        "div[role='alertdialog'] button:has-text('Delete')",
        "button[data-test-id*='confirm-delete' i]",
        "button[aria-label*='Confirm' i]",
    ]

    # Conversation title elements inside current chat or sidebar
    CONVERSATION_TITLE_ELEMENTS = [
        "div[data-test-id='conversation-title']",
        "div.conversation-title",
        "span.conversation-title",
        "span.title",
    ]

    # -- Login / Authentication page detection -------------------
    LOGIN_INDICATORS = [
        "a[href*='accounts.google.com/ServiceLogin']",
        "a:has-text('Sign in')",
        "button:has-text('Sign in')",
    ]

    # -- Logged-in indicator (profile, account menu, top bar) ----
    LOGGED_IN_INDICATORS = [
        "a[aria-label*='Google Account:' i]",
        "a.mavatar-footer-left",
        "img.user-icon",
        "div#gb",
    ]

    # -- Error / no access indicators ----------------------------
    ERROR_INDICATORS = [
        "div:has-text('Something went wrong')",
        "a[href*='p=no_access']",
        "div:has-text('Try again later')",
    ]

    # -- File / Attachment upload input --------------------------
    ATTACH_BUTTON = [
        "button[aria-label*='Upload & tools' i]",
        "button:has(mat-icon[data-mat-icon-name='plus'])",
        "button:has(mat-icon[fonticon='plus'])",
    ]

    UPLOAD_FILES_MENU_BUTTON = [
        "button[data-test-id='local-images-files-uploader-button']",
        "button[role='menuitem']:has-text('Upload files')",
        "button:has-text('Upload files')",
    ]

    FILE_UPLOAD_INPUT = [
        "input[type='file'].hidden-file-input",
        "input[type='file']",
    ]

    # -- Attachment previews and badges in composer --------------
    ATTACHMENT_BADGE = [
        "uploader-file-preview",
        "uploader-file-preview-container",
        "gem-media-attachment",
        "div.file-preview-chip",
        "div.attachment-preview-wrapper",
        "images-files-uploader",
        "uploader",
        ".attachment-container",
        "mat-chip-row",
        "mat-basic-chip",
        "div[class*='attachment']",
        "div[class*='file-preview']",
    ]

    # -- Upload spinner indicating attachment still processing ---
    ATTACHMENT_SPINNER = [
        "uploader-file-preview mat-progress-spinner",
        "uploader mat-progress-spinner",
        "uploader-file-preview [role='progressbar']",
        "uploader-file-preview .mdc-circular-progress",
        "gem-media-attachment mat-progress-spinner",
        "gem-media-attachment [role='progressbar']",
        "gem-media-attachment .mdc-circular-progress",
        ".attachment-preview-wrapper mat-progress-spinner",
        ".attachment-preview-wrapper [role='progressbar']",
        ".attachment-preview-wrapper .mdc-circular-progress",
        "div.file-preview-container mat-progress-spinner",
        "mat-mdc-progress-spinner",
        ".attachment-preview-wrapper mat-progress-spinner",
        "div.file-preview-container [role='progressbar']",
        "div[data-test-id='send-button-container'] mat-progress-spinner",
        "div[data-test-id='send-button-container'] [role='progressbar']",
        "div[data-test-id='send-button-container'] .mdc-circular-progress",
    ]

