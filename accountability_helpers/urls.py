from django.urls import path
from . import views


urlpatterns = [
    path('pdf/generate/', views.generate_pdf, name='generate_pdf'),
    path('pdf/info/', views.get_pdf_info, name='get_pdf_info'),
    path('pdf/<uuid:debt_plan_id>/download/', views.download_pdf, name='download_pdf'),
    path('letter/create/', views.create_letter, name='create_letter'),
    path('letter/', views.get_letter, name='get_letter'),
    path('letter/<uuid:letter_id>/update/', views.update_letter, name='update_letter'),
    path('letter/<uuid:letter_id>/delete/', views.delete_letter, name='delete_letter'),
]