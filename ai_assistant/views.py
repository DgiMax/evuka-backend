# ai_assistant/views.py

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import transaction

from courses.models import Course, Lesson
from .models import ChatHistory

import google.generativeai as genai

# ---------------------------------------------------------------------
# GEMINI INITIALIZATION
# ---------------------------------------------------------------------

GEMINI_API_KEY = getattr(settings, "GEMINI_API_KEY", None)
GEMINI_MODEL_NAME = "gemini-2.5-flash"

AI_SERVICE_READY = False

try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        AI_SERVICE_READY = True
    else:
        raise ValueError("Gemini API key missing")
except Exception:
    AI_SERVICE_READY = False


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def build_system_instruction(course_title: str, lesson_title: str | None):
    """Builds the dynamic system prompt for the tutor."""
    base = (
        f"You are Vusela, a professional E-Learning Tutor for the course '{course_title}'. "
        "Your role is to guide, encourage, and help users understand the course content. "
        "Stay concise and strictly aligned to the curriculum. "
        "Decline unrelated questions politely."
    )

    if lesson_title:
        base += f" The current lesson is '{lesson_title}'."

    return base


def model_generate_greeting(course_title: str):
    """Let Gemini create the first message (no hardcoded greeting)."""
    model = genai.GenerativeModel(GEMINI_MODEL_NAME)

    response = model.generate_content(
        f"Generate a warm, short introductory greeting as Vusela, "
        f"the learning assistant for the course '{course_title}'. "
        "Be friendly, supportive, and helpful without being cheesy."
    )

    return response.text or "Hello! I'm Vusela, your learning assistant."


# ---------------------------------------------------------------------
# API: GET CHAT HISTORY
# ---------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_chat_history(request, course_slug):
    if not AI_SERVICE_READY:
        return Response([{
            'role': 'model',
            'text': "AI Service is offline. Please contact support."
        }])

    user = request.user
    course = get_object_or_404(Course, slug=course_slug)

    chat_history_record, created = ChatHistory.objects.get_or_create(
        user=user,
        course=course,
        defaults={'history_json': []}
    )

    # Generate greeting only once (by model)
    if created or not chat_history_record.history_json:
        greeting = model_generate_greeting(course.title)
        chat_history_record.history_json = [{'role': 'model', 'text': greeting}]
        chat_history_record.save()

    return Response(chat_history_record.history_json)


# ---------------------------------------------------------------------
# API: ASK ASSISTANT (POST)
# ---------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def ask_assistant(request):
    if not AI_SERVICE_READY:
        return Response(
            {"error": "AI Service unavailable. Contact support."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    user_question = request.data.get('question')
    course_slug = request.data.get('course_slug')
    lesson_id = request.data.get('lesson_id')

    if not user_question or not course_slug:
        return Response(
            {"error": "Question and course_slug are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user
    course = get_object_or_404(Course, slug=course_slug)

    chat_history_record, _ = ChatHistory.objects.get_or_create(
        user=user,
        course=course,
        defaults={'history_json': []}
    )

    # Prepare context
    lesson_title = None
    if lesson_id:
        try:
            lesson = get_object_or_404(Lesson, pk=lesson_id)
            lesson_title = lesson.title
        except:
            pass

    system_instruction = build_system_instruction(course.title, lesson_title)

    # Convert stored messages -> Gemini format
    gemini_history = [
        {
            "role": msg["role"],
            "parts": [msg["text"]],
        }
        for msg in chat_history_record.history_json
        if msg.get("role") in ["user", "model"]
    ]

    # Create model with system instructions
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL_NAME,
        system_instruction=system_instruction,
    )

    # Start chat
    chat = model.start_chat(history=gemini_history)

    try:
        response = chat.send_message(user_question)
        ai_answer = response.text

        # Save new messages
        chat_history_record.history_json.append({
            "role": "user",
            "text": user_question
        })
        chat_history_record.history_json.append({
            "role": "model",
            "text": ai_answer
        })
        chat_history_record.save()

        return Response({
            "answer": ai_answer,
            "history": chat_history_record.history_json
        })

    except Exception as e:
        return Response(
            {"error": "AI interaction failed.", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

