import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Config.settings')

app = Celery('Config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


app.conf.beat_schedule = {
    'send-biweekly-motivation': {
        'task': 'accountability_helpers.tasks.send_biweekly_motivation_emails',
        'schedule': crontab(day_of_month='1,15', hour=9, minute=0),  # Every 14 days.
    },
    'send-monthly-progress-report': {
        'task': 'accountability_helpers.tasks.send_monthly_progress_report',
        'schedule': crontab(day_of_month='1', hour=10, minute=0),  # 1st of month at 10 AM
    },
    'send-payment-reminders': {
        'task': 'accountability_helpers.tasks.send_payment_reminder',
        'schedule': crontab(day_of_week='friday', hour=14, minute=0),  # Every Friday at 2 PM
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')