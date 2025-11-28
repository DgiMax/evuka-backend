from django.urls import path
from . import views

urlpatterns = [
    path("history/<str:course_slug>/", views.get_chat_history, name="ai-get-history"),
    path("ask/", views.ask_assistant, name="ai-ask-assistant"),
]