from django.urls import path
from .views import *
from invoicing.api import verify_professional, verify_passcode

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('home/', IndexView.as_view(), name='index'),
    path('contact-us/', ContactUsView.as_view(), name='contact-us'),
    path('about-us/', AboutUsView.as_view(), name='about-us'),
    path('privacy-policy/', PrivacyPolicyView.as_view(), name='privacy-policy'),
    path('terms-and-conditions/', TermsAndConditionsView.as_view(), name='terms-and-conditions'),
    path('cancellation/', CancellationView.as_view(), name='cancellation'),
    path('invoice-reports/<str:recipient_id>/', InvoiceReportsView.as_view(), name='invoice-reports'),
    
    # API endpoints
    path('api/verify-professional/', verify_professional, name='verify-professional'),
    path('api/verify-passcode/', verify_passcode, name='verify-passcode'),
]

