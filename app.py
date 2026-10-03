import smtplib
import secrets
import time
import re
from datetime import datetime
from email.message import EmailMessage

import streamlit as st
from google import genai
from google.genai import types

from prompts import (
    SUMMARY_REQUEST_PROMPT,
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
)

from database import (
    initialize_database,
    save_visited_place,
    get_visited_places,
)

# =========================================================
# APP CONFIGURATION
# =========================================================

MODEL_NAME = "gemini-3.5-flash-lite"

# Temporary local-development setting.
# True = skip email verification while we build the app.
# Change to False before final deployment.
DEVELOPMENT_MODE = False

st.set_page_config(
    page_title="Place History Explorer",
    page_icon="📍",
    layout="centered",
)
# =========================================================
# CUSTOM UI STYLING
# =========================================================

st.markdown(
    """
    <style>

    /* -----------------------------------------------------
       DARK BACKGROUND
    ----------------------------------------------------- */

    [data-testid="stAppViewContainer"] {
        background: #121722;
    }
    /* Main application width */
    .block-container {
        max-width: 900px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    /* Main headings */
    h1 {
        font-weight: 700;
        letter-spacing: -0.5px;
    }

    h2 {
        font-weight: 650;
    }

    h3 {
        font-weight: 600;
    }

    /* Input fields */
    div[data-baseweb="input"] input {
        font-size: 16px;
    }

    /* Buttons */
    div.stButton > button {
        border-radius: 10px;
        min-height: 44px;
        font-weight: 600;
    }

    /* File uploader */
    section[data-testid="stFileUploaderDropzone"] {
        border-radius: 12px;
    }

    /* Expanders */
    div[data-testid="stExpander"] {
        border-radius: 12px;
    }

    /* Chat messages */
    div[data-testid="stChatMessage"] {
        border-radius: 12px;
        padding: 0.75rem 1rem;
    }

    /* Captions */
    .stCaption {
        font-size: 14px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# SECRETS
# =========================================================

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GMAIL_ADDRESS = st.secrets["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = st.secrets["GMAIL_APP_PASSWORD"]


# =========================================================
# GEMINI CLIENT
# =========================================================

@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)


gemini_client = get_gemini_client()
initialize_database()

# =========================================================
# SESSION STATE
# =========================================================

if "onboarded" not in st.session_state:
    st.session_state.onboarded = False

if "verification_sent" not in st.session_state:
    st.session_state.verification_sent = False

if "verification_code" not in st.session_state:
    st.session_state.verification_code = ""

if "verification_email" not in st.session_state:
    st.session_state.verification_email = ""

if "verification_time" not in st.session_state:
    st.session_state.verification_time = 0

if "messages" not in st.session_state:
    st.session_state.messages = []

if "visited_places" not in st.session_state:
    st.session_state.visited_places = []

if "last_place_info" not in st.session_state:
    st.session_state.last_place_info = ""


# =========================================================
# HELPER: ASK GEMINI
# =========================================================
def ask_gemini(parts):
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            response = st.session_state.chat.send_message(parts)
            return response.text

        except Exception as error:

            error_text = str(error)

            if "503" in error_text or "UNAVAILABLE" in error_text:

                if attempt < max_attempts - 1:
                    time.sleep(2 ** attempt)
                    continue

                return (
                    "Gemini is temporarily busy right now. "
                    "Please try your question again in a moment."
                )

            return (
                f"Sorry, something went wrong: {error}"
            )

    return "Please try again in a moment."

# =========================================================
# HELPER: LOAD SAVED PLACES
# =========================================================

def load_saved_places(user_email):
    rows = get_visited_places(user_email)

    return [
        {
            "id": row["id"],
            "location": row["location"],
            "date": row["visit_date"],
            "photo": bytes(row["photo"]),
            "history": row["history"],
        }
        for row in rows
    ]

# =========================================================
# HELPER: ADD MESSAGE
# =========================================================

def add_message(role, kind, content):
    st.session_state.messages.append(
        {
            "role": role,
            "kind": kind,
            "content": content,
        }
    )


# =========================================================
# HELPER: DISPLAY MESSAGE
# =========================================================

def render_message(message):

    with st.chat_message(message["role"]):

        if message["kind"] == "image":

            st.image(message["content"])

        else:

            st.write(message["content"])

         # =========================================================
# HELPER: CREATE HISTORY EMAIL SUMMARY
# =========================================================

def create_history_summary():

    if not st.session_state.visited_places:
        return None

    # -----------------------------------------------------
    # SAVED PLACES
    # -----------------------------------------------------

    saved_places = []

    for place in st.session_state.visited_places:

        saved_places.append(
            f"""
Place: {place["location"]}
Date visited: {place["date"]}

History:
{place["history"]}
"""
        )

    all_places_text = "\n\n--------------------\n\n".join(
        saved_places
    )

    # -----------------------------------------------------
    # CONVERSATION / FOLLOW-UP QUESTIONS
    # -----------------------------------------------------

    conversation_parts = []

    for message in st.session_state.messages:

        if message["kind"] != "text":
            continue

        role = message["role"]
        content = message["content"]

        # Ignore the initial welcome message.
        if (
            role == "assistant"
            and content.startswith("Hello ")
            and "Welcome to Place History Explorer" in content
        ):
            continue

        if role == "user":

            conversation_parts.append(
                f"""
User question:
{content}
"""
            )

        elif role == "assistant":

            conversation_parts.append(
                f"""
Assistant answer:
{content}
"""
            )

    conversation_text = "\n\n".join(
        conversation_parts
    )

    # -----------------------------------------------------
    # GEMINI SUMMARY PROMPT
    # -----------------------------------------------------

    prompt = f"""
{SUMMARY_REQUEST_PROMPT}

Here are the user's saved places:

{all_places_text}

Here is the text conversation containing questions
and follow-up answers about those places:

{conversation_text}

Create the final travel-history email.

For each saved place:
- Include the place name and location.
- Include the date visited.
- Include the important historical information.
- Include the architectural or cultural significance.
- Include interesting facts.

Also include a section called:

💬 Follow-up Questions

For each meaningful follow-up question about a saved place:
- Show the user's question.
- Give a concise version of the assistant's answer.

Do not include the initial welcome message.
Do not include unrelated conversation.
Do not invent information.
Only use information contained in the saved place records
and conversation above.

Keep the email clean, readable, and concise.
Start with a friendly introduction.
Finish with:

Keep exploring!
"""

    # -----------------------------------------------------
    # GENERATE SUMMARY
    # -----------------------------------------------------

    try:

        summary_chat = gemini_client.chats.create(
            model=MODEL_NAME,
        )

        response = summary_chat.send_message(
            prompt
        )

        return response.text

    except Exception as error:

        return (
            f"Could not create the email summary: {error}"
        )
# =========================================================
# HELPER: SEND EMAIL
# =========================================================

def send_email(to_address, subject, body):

    try:
        message = EmailMessage()

        message["From"] = GMAIL_ADDRESS
        message["To"] = to_address
        message["Subject"] = subject

        message.set_content(body)

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
        ) as server:

            server.login(
                GMAIL_ADDRESS,
                GMAIL_APP_PASSWORD,
            )

            server.send_message(message)

        return True, "Email sent successfully."

    except Exception as error:

        return False, str(error)


# =========================================================
# HELPER: SEND VERIFICATION CODE
# =========================================================

def send_verification_code(to_address, code):

    subject = (
        "Your Place History Explorer verification code"
    )

    body = f"""
Hello!

Your Place History Explorer verification code is:

{code}

This code will expire in 5 minutes.

If you did not request this code, you can safely ignore this email.

Place History Explorer
"""

    return send_email(
        to_address,
        subject,
        body,
    )


# =========================================================
# ONBOARDING + EMAIL VERIFICATION
# =========================================================

if not st.session_state.onboarded:

    st.title("📍 Place History Explorer")

    st.subheader(
        "Discover the story behind the places you visit."
    )

    # =====================================================
    # STEP 1: NAME + EMAIL
    # =====================================================

    if not st.session_state.verification_sent:

        st.write(
            "Enter your name and email to get started."
        )

        with st.form("onboarding_form"):

            name = st.text_input(
                "Your name",
                placeholder="Enter your name",
            )

            email = st.text_input(
                "Your email",
                placeholder="example@gmail.com",
            )

            submitted = st.form_submit_button(
                "Send Verification Code 📧",
                use_container_width=True,
            )

        if submitted:

            if not name.strip() or not email.strip():

                st.warning(
                    "Please enter both your name and email."
                )

            else:

                st.session_state.name = name.strip()
                st.session_state.email = email.strip()

                # =================================================
                # TEMPORARY DEVELOPMENT MODE
                # =================================================

                if DEVELOPMENT_MODE:

                    st.session_state.chat = (
                        gemini_client.chats.create(
                            model=MODEL_NAME,
                            config=types.GenerateContentConfig(
                                system_instruction=SYSTEM_PROMPT
                            ),
                        )
                    )

                    st.session_state.messages = []
                    st.session_state.last_place_info = ""
                    st.session_state.visited_places = load_saved_places(
                        st.session_state.email
                    )

                    st.session_state.onboarded = True

                    st.rerun()

                # =================================================
                # NORMAL MODE: EMAIL VERIFICATION
                # =================================================

                else:

                    verification_code = str(
                        secrets.randbelow(900000) + 100000
                    )

                    success, info = send_verification_code(
                        email.strip(),
                        verification_code,
                    )

                    if success:

                        st.session_state.verification_email = (
                            email.strip()
                        )

                        st.session_state.verification_code = (
                            verification_code
                        )

                        st.session_state.verification_time = (
                            time.time()
                        )

                        st.session_state.verification_sent = True

                        st.rerun()

                    else:

                        st.error(
                            f"Could not send verification email: {info}"
                        )


    # =====================================================
    # STEP 2: VERIFY EMAIL
    # =====================================================

    else:

        st.info(
            f"📧 We sent a 6-digit verification code to "
            f"{st.session_state.verification_email}"
        )

        st.write(
            "Enter the code from your email below."
        )

        with st.form("verification_form"):

            entered_code = st.text_input(
                "Verification code",
                placeholder="Enter 6-digit code",
                max_chars=6,
            )

            verify_button = st.form_submit_button(
                "Verify Email ✅",
                use_container_width=True,
            )

        # =================================================
        # VERIFY CODE
        # =================================================

        if verify_button:

            elapsed_time = (
                time.time()
                - st.session_state.verification_time
            )

            # Code expires after 5 minutes
            if elapsed_time > 300:

                st.error(
                    "This verification code has expired. "
                    "Please request a new code."
                )
            # Empty code
            if not entered_code.strip():

                st.warning(
                    "Please enter the 6-digit verification code."
                )
            # Wrong code
            elif entered_code.strip() != (
                st.session_state.verification_code
            ):

                st.error(
                    "Incorrect verification code. "
                    "Please try again."
                )

            # Correct code
            else:

                st.success(
                    "Email verified successfully! ✅"
                )

                st.session_state.email = (
                    st.session_state.verification_email
                )

                st.session_state.chat = (
                    gemini_client.chats.create(
                        model=MODEL_NAME,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT
                        ),
                    )
                )

                st.session_state.messages = []
                st.session_state.last_place_info = ""
                st.session_state.visited_places = load_saved_places(
                    st.session_state.email
                )
                st.session_state.onboarded = True

                st.rerun()

        # =================================================
        # RESEND CODE
        # =================================================

        st.caption(
            "Didn't receive the code?"
        )

        if st.button(
            "Resend Verification Code 📧",
            use_container_width=True,
        ):

            new_code = str(
                secrets.randbelow(900000) + 100000
            )

            success, info = send_verification_code(
                st.session_state.verification_email,
                new_code,
            )

            if success:

                st.session_state.verification_code = (
                    new_code
                )

                st.session_state.verification_time = (
                    time.time()
                )

                st.success(
                    "A new verification code has been sent. 📧"
                )

                st.rerun()

            else:

                st.error(
                    f"Could not send verification email: {info}"
                )

    # Stop here until the user is verified
    st.stop()


# =========================================================
# MAIN HEADER
# =========================================================

header_col, button_col = st.columns(
    [5, 2],
    vertical_alignment="center",
)

with header_col:

    st.title(
        "📍 Place History Explorer"
    )
with button_col:

    send_disabled = (
        len(st.session_state.visited_places) == 0
    )

    if st.button(
        "📧 Send History",
        disabled=send_disabled,
        use_container_width=True,
    ):

        with st.spinner(
            "Preparing your travel history..."
        ):

            summary = create_history_summary()


        if summary:

            success, info = send_email(
                st.session_state.email,
                "Your Place History Explorer Travel History",
                summary,
            )

            if success:

                st.success(
                    "Your travel history has been sent! 📧"
                )

            else:

                st.error(
                    f"Couldn't send the email: {info}"
                )

        else:

            st.warning(
                "You don't have any saved places yet."
            )
# =========================================================
# USER INFORMATION
# =========================================================

st.caption(
    f"Logged in as {st.session_state.name} "
    f"• History will be sent to {st.session_state.email}"
)
# =========================================================
# WELCOME MESSAGE
# =========================================================

if not st.session_state.messages:

    add_message(
        "assistant",
        "text",
        WELCOME_MESSAGE_TEMPLATE.format(
            name=st.session_state.name
        ),
    )


# =========================================================
# DISPLAY CHAT HISTORY
# =========================================================

for message in st.session_state.messages:

    render_message(message)

# =========================================================
# EXPLORE A PLACE
# =========================================================

st.markdown("## 🌍 Explore a Place")

st.caption(
    "Enter the location if you know it, then upload a photo "
    "or ask a question about the place."
)

location = st.text_input(
    "📍 Place or location",
    placeholder="Example: Taj Mahal, Agra",
    help=(
        "Adding the place name helps the assistant give "
        "more accurate historical information."
    ),
)


# =========================================================
# PHOTO + CHAT INPUT
# =========================================================

user_input = st.chat_input(
    "💬 Ask about this place or attach a photo",
    accept_file=True,
    file_type=[
        "jpg",
        "jpeg",
        "png",
    ],
)

# =========================================================
# MY VISITED PLACES
# =========================================================

st.markdown("## 🗺️ My Visited Places")

place_count = len(st.session_state.visited_places)

st.caption(
    f"{place_count} "
    f"place{'s' if place_count != 1 else ''} saved"
)

if not st.session_state.visited_places:

    st.info(
        "No places saved yet. Upload a photo of a place to start your travel history."
    )

else:

    places = list(
        reversed(st.session_state.visited_places)
    )

    columns = st.columns(2)

    for index, place in enumerate(places):

        with columns[index % 2]:

            with st.container(border=True):

                # -----------------------------------------
                # PHOTO
                # -----------------------------------------

                st.image(
                    place["photo"],
                    width="stretch",
                )

                # -----------------------------------------
                # PLACE NAME
                # -----------------------------------------

                st.markdown(
                    f"### 📍 {place['location']}"
                )

                # -----------------------------------------
                # DATE
                # -----------------------------------------

                st.caption(
                    f"📅 Visited: {place['date']}"
                )

                # -----------------------------------------
                # HISTORY
                # -----------------------------------------

                with st.expander(
                    "📖 Read Place History"
                ):

                    # Remove Markdown heading symbols
                    # so Gemini's ### headings don't become
                    # huge titles inside the card.
                    clean_history = re.sub(
                        r"^\s*#{1,6}\s*",
                        "",
                        place["history"],
                        flags=re.MULTILINE,
                    )

                    st.markdown(
                        clean_history
                    )


# =====================================================
# PROCESS USER INPUT
# =====================================================

if user_input:

    photo = (
        user_input.files[0]
        if user_input.files
        else None
    )

    text = user_input.text

    parts = []

    # =====================================================
    # PHOTO
    # =====================================================

    if photo is not None:

        photo_bytes = photo.getvalue()

        add_message(
            "user",
            "image",
            photo_bytes,
        )

        parts.append(
            types.Part.from_bytes(
                data=photo_bytes,
                mime_type=photo.type,
            )
        )

    # =====================================================
    # USER TEXT
    # =====================================================

    if text:

        add_message(
            "user",
            "text",
            text,
        )

        # If the user is asking a follow-up question about
        # the previously analyzed place, explicitly provide
        # the previous place information as context.
        if (
            photo is None
            and st.session_state.last_place_info
        ):

            parts.append(
                f"""
We are continuing the conversation about the place
that was analyzed previously.

Here is the previous place analysis:

{st.session_state.last_place_info}

The user is now asking this follow-up question:

{text}

Answer the follow-up question using the previous
place analysis as context. Do not ask the user to
upload the photo again unless the question truly
requires information that is not available.
"""
            )

        else:

            parts.append(text)

    # =====================================================
    # PHOTO WITHOUT TEXT
    # =====================================================

    elif photo is not None:

        if location.strip():

            parts.append(
                f"""
The user says this photo is from:

{location.strip()}

Analyze the photo and explain what place it appears to be.

Provide:
- Place name
- Location
- Historical background
- Important dates or historical events
- Architectural or cultural significance
- Interesting facts

Do not invent information.

If the place cannot be reliably identified,
clearly say so.
"""
            )

        else:

            parts.append(
                """
Analyze this place carefully.

Try to identify the landmark, monument,
building, historical site, or location
shown in the photo.

Provide:
- Place name
- Location if it can be determined
- Historical background
- Important dates or historical events
- Architectural or cultural significance
- Interesting facts

Do not invent information.

If the place cannot be reliably identified
from the photo, clearly say so.
"""
            )

    # =====================================================
    # SEND TO GEMINI
    # =====================================================

    with st.spinner(
        "Exploring the history of this place..."
    ):

        answer = ask_gemini(parts)

    # =====================================================
    # DISPLAY / SAVE AI RESPONSE
    # =====================================================

    add_message(
        "assistant",
        "text",
        answer,
    )

    st.session_state.last_place_info = answer

    # =====================================================
    # SAVE VISITED PLACE
    # =====================================================

    if photo is not None:

        if location.strip():

            saved_location = location.strip()

        elif text.strip() and len(text.strip()) <= 60:

            saved_location = text.strip()

        else:

            saved_location = "Place identified from photo"

        visit_date = datetime.now().strftime(
            "%B %d, %Y"
        )

        # Save permanently to the database
        save_visited_place(
            user_email=st.session_state.email,
            location=saved_location,
            visit_date=visit_date,
            photo=photo_bytes,
            history=answer,
        )

        # Update the current session immediately
        st.session_state.visited_places.insert(
            0,
            {
                "location": saved_location,
                "date": visit_date,
                "photo": photo_bytes,
                "history": answer,
            },
        )

        st.success(
            f"✅ {saved_location} has been saved to My Visited Places."
        )

    st.rerun()
