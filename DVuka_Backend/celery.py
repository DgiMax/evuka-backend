import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DVuka_Backend.settings')

app = Celery('DVuka_Backend')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

app.conf.beat_schedule = {
    'generate-daily-lessons-midnight': {
        'task': 'live.tasks.trigger_daily_schedule_updates',
        'schedule': crontab(minute=0, hour=0),
    },
}

# -------------------------------------------------------------------------
# CELERY & REDIS SETUP GUIDE (WINDOWS/DOCKER)
# -------------------------------------------------------------------------
# To run the background tasks (Live Class generation, Emails, etc.), you need
# to run three separate terminals.
#
# 1. INSTALL REQUIREMENTS:
#    pip install celery redis
#
# 2. START REDIS (Message Broker):
#    If using Docker:
#    docker run -d --name redis-broker -p 6379:6379 redis
#
# 3. TERMINAL 1: DJANGO SERVER (Web Requests)
#    python manage.py runserver
#
# 4. TERMINAL 2: CELERY WORKER (Executes Tasks)
#    # Windows requires '--pool=solo' because it lacks 'fork()' support.
#    celery -A DVuka_Backend worker --loglevel=info --pool=solo
#
# 5. TERMINAL 3: CELERY BEAT (Scheduler)
#    # Triggers the daily tasks (e.g., generating future lessons)
#    celery -A DVuka_Backend beat --loglevel=info
# -------------------------------------------------------------------------